from __future__ import annotations

import ast
import difflib
import re
import sys
import tempfile
from pathlib import Path

from verifix.models.evidence import VerificationFinding, VerificationResult, VerificationStatus
from verifix.patching.diff import new_file_diff
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.sandbox.local_sandbox import prepare_workspace
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers._delta import py_files

MAX_MUTANTS = 8
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_SWAP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
         ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.And: ast.Or, ast.Or: ast.And}


def changed_lines(diff: str) -> dict[str, set[int]]:
    """New-file line numbers of every added line, per file."""
    out: dict[str, set[int]] = {}
    path, n = "", 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif m := _HUNK.match(line):
            n = int(m[1])
        elif path and line.startswith("+") and not line.startswith("+++"):
            out.setdefault(path, set()).add(n)
            n += 1
        elif path and not line.startswith("-"):
            n += 1
    return out


def _mutable(node: ast.AST) -> bool:
    return (isinstance(node, ast.Compare | ast.BinOp | ast.BoolOp) or isinstance(node, ast.Return) and node.value is not None
            or isinstance(node, ast.Constant) and isinstance(node.value, bool | int | float))


def _mutate(tree: ast.Module, target: int) -> bool:
    """Apply one mutation to the `target`-th mutable node (in walk order); True if applied."""
    for idx, node in enumerate(n for n in ast.walk(tree) if _mutable(n)):
        if idx != target:
            continue
        if isinstance(node, ast.Compare) and type(node.ops[0]) in _SWAP:
            node.ops[0] = _SWAP[type(node.ops[0])]()
        elif isinstance(node, ast.BinOp) and type(node.op) in _SWAP:
            node.op = _SWAP[type(node.op)]()
        elif isinstance(node, ast.BoolOp):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        elif isinstance(node, ast.Return):
            node.value = ast.Constant(value=None)
        elif isinstance(node, ast.Constant):
            node.value = (not node.value) if isinstance(node.value, bool) else node.value + 1
        else:
            return False
        return True
    return False


class MutationVerifier(Verifier):
    """Does the test suite notice small faults injected into the lines the patch changed?

    A weak score means passing tests are poor evidence for this patch. Experimental signal:
    it can lower confidence (WARNING) but never fails a patch on its own.
    """

    name = "mutation"

    def verify(self, context: VerificationContext) -> VerificationResult:
        wanted = changed_lines(context.patch.diff)
        files = [f for f in py_files(context, existing_only=False) if f in wanted]
        mutants: list[tuple[str, str]] = []  # (description, diff against the base repo)
        with tempfile.TemporaryDirectory(prefix="verifix-mut-") as tmp:
            work = Path(tmp) / "repo"
            if prepare_workspace(ExecutionRequest(repo_path=context.repo_path, patch_diff=context.patch.diff), work):
                return VerificationResult(self.name, VerificationStatus.NOT_RUN, 0.0,
                                          [VerificationFinding("patch does not apply", "info")])
            for rel in files:
                src = (work / rel).read_text()
                nodes = [n for n in ast.walk(ast.parse(src)) if _mutable(n)]
                for idx, node in enumerate(nodes):
                    if getattr(node, "lineno", 0) not in wanted[rel] or len(mutants) >= MAX_MUTANTS:
                        continue
                    tree = ast.parse(src)
                    if _mutate(tree, idx):
                        mutants.append((f"{rel}:{node.lineno} {type(node).__name__}", self._diff(context.repo_path, rel, ast.unparse(tree) + "\n")))
        if not mutants:
            return VerificationResult(self.name, VerificationStatus.NOT_RUN, 0.0,
                                      [VerificationFinding("no mutable expressions in the changed lines", "info")])
        command = context.issue.test_command or [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
        survived = []
        for label, diff in mutants:
            res = context.sandbox.execute(ExecutionRequest(command=command, repo_path=context.repo_path, patch_diff=diff,
                                                           limits=ResourceLimits(timeout_seconds=60)))
            if res.exit_code == 0 and not res.timed_out:
                survived.append(label)
        score = 1 - len(survived) / len(mutants)
        findings = [VerificationFinding(f"mutation score {score:.2f} ({len(mutants) - len(survived)}/{len(mutants)} mutants killed)", "info")]
        findings += [VerificationFinding(f"surviving mutant (tests did not notice): {s}", "warning", s) for s in survived]
        return VerificationResult(self.name, VerificationStatus.PASS if score >= 0.6 else VerificationStatus.WARNING,
                                  round(score, 2) or 0.1, findings)

    @staticmethod
    def _diff(base_repo: str, rel: str, mutated: str) -> str:
        """Diff from the BASE repo to the mutated patched file (replaces the patch for that run)."""
        base = Path(base_repo, rel)
        if not base.is_file():
            return new_file_diff(rel, mutated)
        old = base.read_text().splitlines(keepends=True)
        body = "".join(difflib.unified_diff(old, mutated.splitlines(keepends=True), f"a/{rel}", f"b/{rel}"))
        return f"diff --git a/{rel} b/{rel}\n{body}"



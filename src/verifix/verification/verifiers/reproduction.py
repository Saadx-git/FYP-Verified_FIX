from __future__ import annotations

import sys
from pathlib import Path

from verifix.llm.client import GroqClient
from verifix.models.evidence import (
    Evidence,
    VerificationFinding,
    VerificationResult,
    VerificationStatus,
)
from verifix.patching.diff import new_file_diff
from verifix.repository.context_retriever import ContextRetriever
from verifix.repository.file_inspector import FileInspector
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers._llm import ask_json, issue_text
from verifix.verification.verifiers.unit_test import collect_tests, parse_outcomes, pytest_cmd

TEST_PATH = "tests/test_verifix_repro.py"
SYSTEM = (
    "You write a minimal pytest reproduction test for a bug report. The test must FAIL on the current (buggy) code "
    "and PASS once the bug is fixed. Rules: use only the public behaviour described in the report; 1-4 small "
    "deterministic test functions; import from the repository the same way the existing tests do; no mocks of "
    "internals; no network or file writes; do not assume how the fix is implemented. Assert ONLY behaviour the report "
    "explicitly states or gives an example of; never add edge cases the report does not mention (negative, zero, huge or "
    "empty inputs, other types, error handling) and never decide business rules yourself; if the report is vague, test the "
    "single most direct example it implies and follow the conventions shown by the existing tests. "
    'Respond with JSON: {"test_code": str}'
)


class ReproductionVerifier(Verifier):
    """Independently generated reproduction test: must fail before the patch and pass after.

    Gives issues that come with no failing test (typed text, GitHub issues) real before/after evidence.
    Written from the issue and the ORIGINAL code only, never from the patch or the agent's reasoning.
    """

    name = "reproduction"

    def __init__(self, client: GroqClient, model: str) -> None:
        self.client, self.model = client, model
        self._cache: dict[str, tuple[str, int, str]] = {}  # issue_id -> (test code, tokens, problem)

    def verify(self, context: VerificationContext) -> VerificationResult:
        issue = context.issue
        if issue.fail_to_pass:
            return VerificationResult(self.name, VerificationStatus.NOT_RUN, 0.0,
                                      [VerificationFinding("issue already names failing tests", "info")])
        tokens = 0
        if issue.issue_id not in self._cache:
            self._cache[issue.issue_id] = self._generate(context)
            tokens = self._cache[issue.issue_id][1]
        code, _, problem = self._cache[issue.issue_id]
        if not code:
            return VerificationResult(self.name, VerificationStatus.UNCERTAIN, 0.0,
                                      [VerificationFinding(problem, "warning")], cost=tokens)
        test_diff = new_file_diff(TEST_PATH, code)
        patched = context.patch.diff.rstrip("\n") + "\n" + test_diff if context.patch.diff.strip() else test_diff
        after = self._run(context, patched)
        outcomes = parse_outcomes(after.stdout)
        tests, _ = collect_tests(after.stdout, role="reproduction")
        failed = [t for t, o in outcomes.items() if o != "PASSED"]
        evidence = [Evidence(self.name, "pytest_output", after.stdout[-3000:])]
        if outcomes and not failed:
            return VerificationResult(self.name, VerificationStatus.PASS, 0.8,
                                      [VerificationFinding(f"reproduction test passes after the patch ({len(outcomes)} checks)", "info")],
                                      evidence, tokens, after.duration_seconds, tests)
        msgs = [f"reproduction test still fails: {t}" for t in failed] or ["reproduction test could not run on the patched code"]
        return VerificationResult(self.name, VerificationStatus.FAIL, 0.8,
                                  [VerificationFinding(m, "error") for m in msgs], evidence, tokens, after.duration_seconds, tests)

    def _run(self, context: VerificationContext, diff: str):
        return context.sandbox.execute(ExecutionRequest(
            command=pytest_cmd([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", TEST_PATH]),
            repo_path=context.repo_path, patch_diff=diff, limits=ResourceLimits(timeout_seconds=120)))

    def _generate(self, context: VerificationContext) -> tuple[str, int, str]:
        """Write the test, then validate it fails on the original code (retry once with the failure output)."""
        tokens, feedback = 0, ""
        prompt = f"{issue_text(context)}\n\n{self._code_context(context)}"
        for _ in range(2):
            data, used = ask_json(self.client, self.model, SYSTEM, prompt + feedback, "reproduction")
            tokens += used
            code = str(data.get("test_code", "")).strip()
            if not code:
                return "", tokens, "could not generate a reproduction test"
            baseline = self._run(context, new_file_diff(TEST_PATH, code))
            outcomes = parse_outcomes(baseline.stdout)
            failed = [t for t, o in outcomes.items() if o == "FAILED"]
            errored = [t for t, o in outcomes.items() if o == "ERROR"]
            if failed and not errored:
                return code, tokens, ""
            why = ("it errored instead of failing:\n" + baseline.stdout[-800:]) if errored or not outcomes else \
                "it passes on the buggy code, so it does not reproduce the bug"
            feedback = f"\n\nYour previous test was invalid: {why}\nWrite a corrected test."
        return "", tokens, "generated reproduction test was not valid (it did not fail cleanly on the original code)"

    @staticmethod
    def _code_context(context: VerificationContext) -> str:
        repo, parts = Path(context.repo_path), []
        for rel, line in ContextRetriever().retrieve(context.repo_path, context.issue)["locations"][:2]:
            start = max(line - 40, 1)
            parts.append(f"Current code around {rel}:{line}:\n"
                         + FileInspector().read_file(str(repo / rel), start=start, end=start + 80, max_lines=80))
        tests = sorted((repo / "tests").glob("test_*.py")) if (repo / "tests").is_dir() else []
        shown = "\n\n".join(f"# {t.relative_to(repo)}\n{t.read_text()[:1500]}" for t in tests[:3])[:3500]
        if shown:
            parts.append("Existing tests show the project's conventions and intended behaviour; follow their import style and "
                         f"do not contradict them:\n{shown}")
        return "\n\n".join(parts)

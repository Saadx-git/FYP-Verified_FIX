from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.verification.verifiers.unit_test import parse_outcomes


def oracle_check(inst: dict, diff: str) -> tuple[bool, bool]:
    """Ground truth for an instance: (patch is correct, patch caused a regression).

    Correct = the full test suite plus held-out `oracle_files` (never shown to the agent or the
    verifiers) pass with the patch applied. Regression = a `pass_to_pass` test no longer passes.
    """
    if not diff.strip():
        return False, False
    with tempfile.TemporaryDirectory(prefix="verifix-oracle-") as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(inst["repo"], repo, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".verifix"))
        for rel, content in inst.get("oracle_files", {}).items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(content)
        res = LocalSandbox().execute(ExecutionRequest(
            command=inst.get("oracle_command") or [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider"],
            repo_path=str(repo), patch_diff=diff, limits=ResourceLimits(timeout_seconds=180)))
    outcomes = parse_outcomes(res.stdout)
    p2p = inst.get("pass_to_pass", [])
    regression = any(not any(t.endswith(w) or w in t for t, o in outcomes.items() if o == "PASSED") for w in p2p)
    return res.exit_code == 0 and bool(outcomes), regression

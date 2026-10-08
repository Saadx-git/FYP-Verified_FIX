from __future__ import annotations

import re
import sys

from verifix.models.evidence import (
    Evidence,
    VerificationFinding,
    VerificationResult,
    VerificationStatus,
)
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.verification.base import VerificationContext, Verifier

_LINE = re.compile(r"^(PASSED|FAILED|ERROR)\s+(\S+)")


class UnitTestVerifier(Verifier):
    """Runs pytest on the patched repo; target tests must pass, others must not regress."""

    name = "unit_tests"

    def verify(self, context: VerificationContext) -> VerificationResult:
        issue = context.issue
        command = issue.test_command or [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider"]
        res = context.sandbox.execute(
            ExecutionRequest(
                command=command, repo_path=context.repo_path,
                patch_diff=context.patch.diff, limits=ResourceLimits(timeout_seconds=120),
            )
        )
        evidence = [Evidence(source=self.name, kind="pytest_output", content=res.stdout[-4000:])]
        if res.timed_out or "patch failed to apply" in res.stderr:
            msg = "tests timed out" if res.timed_out else res.stderr.strip()
            return VerificationResult(
                self.name, VerificationStatus.FAIL, 1.0,
                [VerificationFinding(msg, "error")], evidence, 0.0, res.duration_seconds,
            )

        outcomes = {m[2]: m[1] for line in res.stdout.splitlines() if (m := _LINE.match(line)) and m[2]}
        passed = [t for t, o in outcomes.items() if o == "PASSED"]
        failed = [t for t, o in outcomes.items() if o != "PASSED"]
        findings: list[VerificationFinding] = []
        for t in failed:
            kind = "target test still failing" if _matches(t, issue.fail_to_pass) else (
                "regression" if _matches(t, issue.pass_to_pass) else "test failure"
            )
            findings.append(VerificationFinding(f"{kind}: {t}", "error", t))
        missing = [t for t in issue.fail_to_pass if not _matches_any(t, outcomes)]
        for t in missing:
            findings.append(VerificationFinding(f"target test not run: {t}", "error", t))
        if not outcomes:
            findings.append(VerificationFinding(f"no tests collected (exit {res.exit_code})", "error"))
        if findings:
            return VerificationResult(
                self.name, VerificationStatus.FAIL, 1.0, findings, evidence, 0.0, res.duration_seconds
            )
        return VerificationResult(
            self.name, VerificationStatus.PASS, 1.0,
            [VerificationFinding(f"{len(passed)} passed", "info")], evidence, 0.0, res.duration_seconds,
        )


def _matches(test_id: str, wanted: list[str]) -> bool:
    return any(test_id == w or test_id.endswith(w) or w in test_id for w in wanted)


def _matches_any(wanted: str, outcomes: dict[str, str]) -> bool:
    return any(t == wanted or t.endswith(wanted) or wanted in t for t in outcomes)

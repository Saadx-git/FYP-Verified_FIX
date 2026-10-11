from __future__ import annotations

import sys
from pathlib import Path

from verifix.models.evidence import (
    Evidence,
    VerificationFinding,
    VerificationResult,
    VerificationStatus,
)
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers.unit_test import collect_tests, parse_outcomes, pytest_cmd

INTEGRATION_DIR = "tests/integration"


class IntegrationTestVerifier(Verifier):
    """Runs `tests/integration` (kept out of the unit-test run); NOT_RUN when the repo has none."""

    name = "integration_tests"

    def verify(self, context: VerificationContext) -> VerificationResult:
        if not Path(context.repo_path, INTEGRATION_DIR).is_dir():
            return VerificationResult(self.name, VerificationStatus.NOT_RUN, 0.0,
                                      [VerificationFinding("repository has no tests/integration", "info")])
        res = context.sandbox.execute(ExecutionRequest(
            command=pytest_cmd([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", INTEGRATION_DIR]),
            repo_path=context.repo_path, patch_diff=context.patch.diff, limits=ResourceLimits(timeout_seconds=300)))
        evidence = [Evidence(self.name, "pytest_output", res.stdout[-4000:])]
        outcomes = parse_outcomes(res.stdout)
        tests, _ = collect_tests(res.stdout)
        failed = [t for t, o in outcomes.items() if o != "PASSED"]
        if res.timed_out or failed or not outcomes:
            msgs = ["integration tests timed out"] if res.timed_out else [f"integration failure: {t}" for t in failed] or ["no integration tests ran"]
            return VerificationResult(self.name, VerificationStatus.FAIL, 1.0,
                                      [VerificationFinding(m, "error") for m in msgs], evidence, 0.0, res.duration_seconds, tests)
        return VerificationResult(self.name, VerificationStatus.PASS, 1.0,
                                  [VerificationFinding(f"{len(outcomes)} passed", "info")], evidence, 0.0, res.duration_seconds, tests)

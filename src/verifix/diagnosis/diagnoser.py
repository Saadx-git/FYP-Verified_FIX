from __future__ import annotations

from verifix.models.evidence import PatchAssessment, VerificationStatus
from verifix.models.failure import FailureCategory, FailureDiagnosis, RootCauseHypothesis
from verifix.models.patch import CandidatePatch


class FailureDiagnoser:
    """Localizes and classifies verification failures (rule-based)."""

    def diagnose(self, patch: CandidatePatch, assessment: PatchAssessment) -> FailureDiagnosis:
        files = [f.path for f in patch.changed_files]
        failing = [r for r in assessment.results if r.status is VerificationStatus.FAIL]
        if not failing:
            return FailureDiagnosis(FailureCategory.INSUFFICIENT_TEST_COVERAGE, [
                RootCauseHypothesis("evidence inconclusive; no verifier failed", files, 0.3)])
        first = failing[0]
        raw = "\n".join(str(e.content) for e in first.evidence) or "; ".join(f.message for f in first.findings)
        msgs = [f.message for f in first.findings]
        text = " ".join(msgs).lower()
        if first.verifier_name == "security":
            cat = FailureCategory.SECURITY_VIOLATION
        elif first.verifier_name == "reproduction":
            cat = FailureCategory.ORIGINAL_BUG_UNRESOLVED
        elif first.verifier_name == "requirement":
            cat = FailureCategory.REQUIREMENT_MISMATCH
        elif "patch failed to apply" in text or "timed out" in text or "no tests collected" in text:
            cat = FailureCategory.TEST_ENVIRONMENT_FAILURE
        elif "regression" in text:
            cat = FailureCategory.REGRESSION_INTRODUCED
        elif "target test still failing" in text or "target test not run" in text:
            cat = FailureCategory.ORIGINAL_BUG_UNRESOLVED
        else:
            cat = FailureCategory.INCORRECT_IMPLEMENTATION
        return FailureDiagnosis(cat, [RootCauseHypothesis(
            f"{first.verifier_name}: " + "; ".join(msgs[:3]), files, 0.6)], raw_evidence=raw)

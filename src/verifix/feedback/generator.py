from __future__ import annotations

from verifix.models.failure import FailureCategory, FailureDiagnosis, TargetedFeedback

_ADVICE = {
    FailureCategory.ORIGINAL_BUG_UNRESOLVED: "The reported bug is still present. Re-read the issue's expected behavior and fix the root cause.",
    FailureCategory.REGRESSION_INTRODUCED: "Your change broke previously passing behavior. Preserve existing behavior and edge cases.",
    FailureCategory.INCORRECT_IMPLEMENTATION: "The implementation is incorrect. Revisit the logic of the changed code.",
    FailureCategory.REQUIREMENT_MISMATCH: "The patch does not satisfy a stated requirement of the issue.",
    FailureCategory.SECURITY_VIOLATION: "The patch introduces a security problem. Remove the unsafe construct.",
    FailureCategory.TEST_ENVIRONMENT_FAILURE: "The patch could not be applied or tests could not run. Produce a clean, applicable diff.",
    FailureCategory.DEPENDENCY_CONFIGURATION_ISSUE: "A dependency or configuration problem blocked verification.",
    FailureCategory.INSUFFICIENT_TEST_COVERAGE: "Evidence is inconclusive. Make the fix explicit and verifiable.",
}


class FeedbackGenerator:
    """Turns a diagnosis into targeted feedback for the agent."""

    def __init__(self, mode: str = "targeted") -> None:
        self.mode = mode  # "raw" forwards unprocessed verifier output (the RQ3 / ablation-B comparison)

    def generate(self, diagnosis: FailureDiagnosis) -> TargetedFeedback:
        if self.mode == "raw":
            return TargetedFeedback(summary="Verification failed. Raw output follows.", details=[diagnosis.raw_evidence[-1500:]])
        hyp = diagnosis.hypotheses[0] if diagnosis.hypotheses else None
        if hyp and "produced no changes" in hyp.description:
            return TargetedFeedback(
                summary="Your last attempt made no edits at all. Search the repository for the code the issue describes "
                        "(search, find_symbol, list_dir), read it, and change it. If nothing in the repository matches the issue, say so in your summary.",
                details=[hyp.description], suspected_files=[])
        return TargetedFeedback(
            summary=_ADVICE[diagnosis.category],
            details=[hyp.description] if hyp else [],
            suspected_files=hyp.suspected_files if hyp else [],
        )

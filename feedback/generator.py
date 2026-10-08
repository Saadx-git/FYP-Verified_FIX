from __future__ import annotations

from verifix.models.failure import FailureDiagnosis, TargetedFeedback


class FeedbackGenerator:
    """Turns a diagnosis into targeted feedback for the agent."""

    def generate(self, diagnosis: FailureDiagnosis) -> TargetedFeedback:
        """TODO: Generate targeted feedback."""
        raise NotImplementedError

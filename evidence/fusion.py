from __future__ import annotations

from verifix.models.evidence import PatchAssessment, VerificationDecision, VerificationResult


class EvidenceFusionEngine:
    """Interprets collected evidence into an assessment and a decision."""

    def fuse(self, patch_id: str, results: list[VerificationResult]) -> PatchAssessment:
        """TODO: Combine evidence into a reliability assessment."""
        raise NotImplementedError

    def decide(self, assessment: PatchAssessment) -> VerificationDecision:
        """TODO: Produce a verification decision."""
        raise NotImplementedError

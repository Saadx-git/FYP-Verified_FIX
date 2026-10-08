from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class LLMReviewVerifier(Verifier):
    """Independent LLM review of the patch."""

    name = "llm_review"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement independent LLM review."""
        raise NotImplementedError

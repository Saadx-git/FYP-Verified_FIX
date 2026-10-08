from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class MutationVerifier(Verifier):
    name = "mutation"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement mutation testing."""
        raise NotImplementedError

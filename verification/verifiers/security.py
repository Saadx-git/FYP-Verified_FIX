from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class SecurityVerifier(Verifier):
    name = "security"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement security analysis."""
        raise NotImplementedError

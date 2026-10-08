from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class RequirementVerifier(Verifier):
    """Checks the patch against the issue's requirements."""

    name = "requirement"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement requirement verification."""
        raise NotImplementedError

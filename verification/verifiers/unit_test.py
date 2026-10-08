from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class UnitTestVerifier(Verifier):
    name = "unit_tests"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement unit test verification."""
        raise NotImplementedError

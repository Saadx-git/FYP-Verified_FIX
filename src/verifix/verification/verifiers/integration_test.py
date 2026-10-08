from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class IntegrationTestVerifier(Verifier):
    name = "integration_tests"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement integration test verification."""
        raise NotImplementedError

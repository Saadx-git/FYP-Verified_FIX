from __future__ import annotations

from verifix.models.evidence import VerificationResult
from verifix.verification.base import VerificationContext, Verifier


class StaticAnalysisVerifier(Verifier):
    name = "static_analysis"

    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Implement static analysis verification."""
        raise NotImplementedError

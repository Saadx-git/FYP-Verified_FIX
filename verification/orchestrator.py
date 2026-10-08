from __future__ import annotations

from verifix.evidence.store import EvidenceStore
from verifix.models.evidence import VerificationResult
from verifix.models.strategy import VerificationStrategy
from verifix.verification.base import VerificationContext
from verifix.verification.registry import VerifierRegistry


class VerificationOrchestrator:
    """Runs selected verifiers and records their results."""

    def __init__(self, registry: VerifierRegistry, store: EvidenceStore) -> None:
        self.registry = registry
        self.store = store

    def run(
        self,
        context: VerificationContext,
        strategy: VerificationStrategy,
    ) -> list[VerificationResult]:
        """TODO: Run verifiers per strategy and store results."""
        raise NotImplementedError

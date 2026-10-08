from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.patch import CandidatePatch
from verifix.models.strategy import VerificationStrategy


class VerificationStrategySelector:
    """Chooses which verifiers to run next."""

    def select(self, patch: CandidatePatch, budget: BudgetState) -> VerificationStrategy:
        """TODO: Select a verification strategy."""
        raise NotImplementedError

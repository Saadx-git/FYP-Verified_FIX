from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.patch import CandidatePatch
from verifix.models.strategy import VerificationStrategy
from verifix.strategy.verification_selector import VerificationStrategySelector


class AdaptiveVerificationController:
    """Adapts verification depth based on evidence and budget."""

    def __init__(self, selector: VerificationStrategySelector) -> None:
        self.selector = selector

    def next_strategy(self, patch: CandidatePatch, state: BudgetState) -> VerificationStrategy:
        return self.selector.select(patch, state)

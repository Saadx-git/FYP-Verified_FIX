from __future__ import annotations

from enum import Enum

from verifix.models.cost import BudgetState


class StoppingDecision(Enum):
    CONTINUE = "continue"
    STOP = "stop"


class CostAwareStoppingPolicy:
    """Decides whether another attempt is justified.

    Stops when the attempt cap is hit, any spend limit is exhausted, or (once
    `min_expected_improvement` > 0) the expected gain of another attempt is too low.
    """

    def __init__(self, min_expected_improvement: float = 0.0, budget_exhausted=lambda: False) -> None:
        self.min_expected_improvement = min_expected_improvement
        self.budget_exhausted = budget_exhausted

    def decide(self, state: BudgetState) -> StoppingDecision:
        if state.max_attempts and state.attempt_count >= state.max_attempts:
            return StoppingDecision.STOP
        if self.budget_exhausted():
            return StoppingDecision.STOP
        if self.min_expected_improvement and state.expected_improvement < self.min_expected_improvement:
            return StoppingDecision.STOP
        return StoppingDecision.CONTINUE

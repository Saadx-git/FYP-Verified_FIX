from __future__ import annotations

from enum import Enum

from verifix.models.cost import BudgetState


class StoppingDecision(Enum):
    CONTINUE = "continue"
    STOP = "stop"


class CostAwareStoppingPolicy:
    """Decides whether another attempt is justified."""

    def decide(self, state: BudgetState) -> StoppingDecision:
        """TODO: Compare expected benefit with remaining budget."""
        raise NotImplementedError

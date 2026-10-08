from __future__ import annotations

from verifix.config.models import CostBudget, RetryBudget
from verifix.models.cost import BudgetState, CostRecord


class BudgetTracker:
    """Tracks attempts and spend against the configured budgets."""

    def __init__(self, retry_budget: RetryBudget, cost_budget: CostBudget) -> None:
        self.retry_budget = retry_budget
        self.cost_budget = cost_budget

    def record(self, cost: CostRecord) -> None:
        """TODO: Record spend for an attempt."""
        raise NotImplementedError

    def state(self) -> BudgetState:
        """TODO: Return the current budget state."""
        raise NotImplementedError

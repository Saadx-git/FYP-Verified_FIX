from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.failure import FailureDiagnosis
from verifix.models.strategy import RepairStrategy


class RepairStrategySelector:
    """Chooses the next repair strategy."""

    def select(self, diagnosis: FailureDiagnosis, budget: BudgetState) -> RepairStrategy:
        """TODO: Select a repair strategy."""
        raise NotImplementedError

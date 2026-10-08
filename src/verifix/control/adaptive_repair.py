from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.failure import FailureDiagnosis
from verifix.models.strategy import RepairStrategy
from verifix.strategy.repair_selector import RepairStrategySelector


class AdaptiveRepairController:
    """Adapts repair behavior based on diagnosis and budget."""

    def __init__(self, selector: RepairStrategySelector) -> None:
        self.selector = selector

    def next_strategy(self, diagnosis: FailureDiagnosis, state: BudgetState) -> RepairStrategy:
        return self.selector.select(diagnosis, state)

from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.failure import FailureCategory, FailureDiagnosis
from verifix.models.strategy import RepairStrategy, RepairStrategyType


class RepairStrategySelector:
    """Chooses the next repair strategy (rule table; adaptive refinements come later)."""

    def __init__(self) -> None:
        self._last: FailureCategory | None = None

    def select(self, diagnosis: FailureDiagnosis, budget: BudgetState) -> RepairStrategy:
        repeated = diagnosis.category == self._last
        self._last = diagnosis.category
        if diagnosis.category in (FailureCategory.TEST_ENVIRONMENT_FAILURE, FailureCategory.DEPENDENCY_CONFIGURATION_ISSUE):
            kind = RepairStrategyType.FIX_ENVIRONMENT
        elif repeated:
            kind = RepairStrategyType.REEXPLORE_REPOSITORY
        elif diagnosis.category is FailureCategory.INCORRECT_IMPLEMENTATION:
            kind = RepairStrategyType.REGENERATE_PATCH
        else:
            kind = RepairStrategyType.REVISE_PATCH
        return RepairStrategy(kind, {"category": diagnosis.category.value})

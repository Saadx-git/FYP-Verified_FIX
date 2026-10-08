from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.failure import FailureCategory, FailureDiagnosis
from verifix.models.strategy import RepairStrategy, RepairStrategyType

_ENV = (FailureCategory.TEST_ENVIRONMENT_FAILURE, FailureCategory.DEPENDENCY_CONFIGURATION_ISSUE)


class RepairStrategySelector:
    """Chooses the next repair strategy from the diagnosis and the repair history.

    The same failure category recurring means the current approach is not working,
    so the selector escalates: revise -> re-explore the repo -> regenerate from scratch.
    """

    def __init__(self) -> None:
        self.history: list[FailureCategory] = []

    def select(self, diagnosis: FailureDiagnosis, budget: BudgetState) -> RepairStrategy:
        repeats = sum(1 for c in self.history if c == diagnosis.category)
        self.history.append(diagnosis.category)
        if diagnosis.category in _ENV:
            kind = RepairStrategyType.FIX_ENVIRONMENT
        elif repeats >= 2:
            kind = RepairStrategyType.REGENERATE_PATCH
        elif repeats == 1:
            kind = RepairStrategyType.REEXPLORE_REPOSITORY
        elif diagnosis.category is FailureCategory.SECURITY_VIOLATION:
            kind = RepairStrategyType.ADDRESS_SECURITY
        elif diagnosis.category is FailureCategory.INCORRECT_IMPLEMENTATION:
            kind = RepairStrategyType.REGENERATE_PATCH
        else:
            kind = RepairStrategyType.REVISE_PATCH
        return RepairStrategy(kind, {"category": diagnosis.category.value, "repeats": repeats})

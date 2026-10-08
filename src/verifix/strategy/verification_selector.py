from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.patch import CandidatePatch
from verifix.models.strategy import VerificationStrategy

# cheapest/fastest signal first so fail-fast can skip expensive verifiers
_ORDER = ["unit_tests", "static_analysis", "security", "integration_tests", "requirement", "llm_review", "mutation"]


class VerificationStrategySelector:
    """Chooses which verifiers to run next."""

    def __init__(self, enabled: list[str] | None = None) -> None:
        self.enabled = enabled or ["unit_tests"]

    def select(self, patch: CandidatePatch, budget: BudgetState) -> VerificationStrategy:
        names = sorted(self.enabled, key=lambda n: _ORDER.index(n) if n in _ORDER else len(_ORDER))
        return VerificationStrategy(verifier_names=names)

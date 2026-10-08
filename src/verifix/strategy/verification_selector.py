from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.patch import CandidatePatch
from verifix.models.strategy import VerificationStrategy

# cheapest/fastest signal first so expensive verifiers can be skipped once a cheap one fails
_ORDER = ["unit_tests", "static_analysis", "security", "reproduction", "integration_tests", "requirement", "llm_review", "mutation"]
_LOW_TOKENS = 5000
_LLM_ONLY = {"llm_review"}


class VerificationStrategySelector:
    """Chooses which verifiers to run next (cost- and risk-aware)."""

    def __init__(self, enabled: list[str] | None = None, adaptive: bool = True) -> None:
        self.enabled = enabled or ["unit_tests"]
        self.adaptive = adaptive

    def select(self, patch: CandidatePatch, budget: BudgetState) -> VerificationStrategy:
        names = sorted(self.enabled, key=lambda n: _ORDER.index(n) if n in _ORDER else len(_ORDER))
        if not self.adaptive:
            return VerificationStrategy(verifier_names=names)
        tokens_left = budget.remaining.tokens
        if tokens_left and tokens_left < _LOW_TOKENS:  # token budget nearly gone: drop advisory LLM review
            names = [n for n in names if n not in _LLM_ONLY]
        return VerificationStrategy(verifier_names=names, parameters={"skip_expensive_on_fail": True})

from __future__ import annotations

from verifix.models.cost import BudgetState
from verifix.models.failure import FailureCategory, FailureDiagnosis
from verifix.models.patch import CandidatePatch
from verifix.models.strategy import VerificationStrategy

# cheapest/fastest signal first so expensive verifiers can be skipped once a cheap one fails
_ORDER = ["unit_tests", "static_analysis", "security", "reproduction", "integration_tests", "requirement", "llm_review", "mutation"]
_LOW_TOKENS = 5000
_LLM_ONLY = {"llm_review"}

# what to check first after each kind of failure: confirm the specific problem is gone before anything else
_FOCUS = {
    FailureCategory.ORIGINAL_BUG_UNRESOLVED: ["reproduction", "unit_tests"],
    FailureCategory.REGRESSION_INTRODUCED: ["unit_tests", "integration_tests"],
    FailureCategory.INCORRECT_IMPLEMENTATION: ["unit_tests", "reproduction"],
    FailureCategory.REQUIREMENT_MISMATCH: ["requirement", "reproduction"],
    FailureCategory.SECURITY_VIOLATION: ["security", "static_analysis"],
    FailureCategory.INSUFFICIENT_TEST_COVERAGE: ["reproduction", "requirement"],
}
_ENVIRONMENT = (FailureCategory.TEST_ENVIRONMENT_FAILURE, FailureCategory.DEPENDENCY_CONFIGURATION_ISSUE)


class VerificationStrategySelector:
    """Chooses which verifiers to run next, and in what order (cost-, risk- and diagnosis-aware).

    After a failed attempt the diagnosis steers the next one: the verifiers that failed (and those that target the
    diagnosed failure) run first, so a still-broken patch fails fast and cheaply. If the failure was environmental
    (patch did not apply, tests could not run), only unit tests run until the environment works.
    """

    def __init__(self, enabled: list[str] | None = None, adaptive: bool = True) -> None:
        self.enabled = enabled or ["unit_tests"]
        self.adaptive = adaptive
        self._focus: list[str] = []
        self._reason = ""
        self._environment_only = False

    def observe(self, diagnosis: FailureDiagnosis, failed_verifiers: list[str]) -> None:
        """Called after each diagnosed failure; shapes the next `select`."""
        if not self.adaptive:
            return
        self._environment_only = diagnosis.category in _ENVIRONMENT
        self._focus = [*failed_verifiers, *_FOCUS.get(diagnosis.category, [])]
        self._reason = f"after {diagnosis.category.value}"

    def select(self, patch: CandidatePatch, budget: BudgetState) -> VerificationStrategy:
        default = sorted(self.enabled, key=lambda n: _ORDER.index(n) if n in _ORDER else len(_ORDER))
        if not self.adaptive:
            return VerificationStrategy(verifier_names=default)
        names = list(default)
        if self._environment_only and "unit_tests" in names:
            names = ["unit_tests"]  # no point spending on the rest until the patch applies and tests run
        elif self._focus:
            first = [n for n in dict.fromkeys(self._focus) if n in names]
            names = first + [n for n in names if n not in first]
        tokens_left = budget.remaining.tokens
        if tokens_left and tokens_left < _LOW_TOKENS:  # token budget nearly gone: drop advisory LLM review
            names = [n for n in names if n not in _LLM_ONLY]
        return VerificationStrategy(verifier_names=names, parameters={
            "skip_expensive_on_fail": True, "focus": list(dict.fromkeys(self._focus)), "reason": self._reason})

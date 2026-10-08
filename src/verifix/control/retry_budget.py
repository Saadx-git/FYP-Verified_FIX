from __future__ import annotations

from verifix.config.models import CostBudget, RetryBudget
from verifix.models.cost import BudgetState, CostRecord


class BudgetTracker:
    """Tracks attempts and spend against the configured budgets."""

    def __init__(self, retry_budget: RetryBudget, cost_budget: CostBudget) -> None:
        self.retry_budget = retry_budget
        self.cost_budget = cost_budget
        self.attempts = 0
        self.spent = CostRecord()

    def record(self, cost: CostRecord) -> None:
        self.attempts += 1
        self.spent.tokens += cost.tokens
        self.spent.api_cost_usd += cost.api_cost_usd
        self.spent.execution_time_seconds += cost.execution_time_seconds
        self.spent.verification_cost += cost.verification_cost

    def state(self) -> BudgetState:
        b, s = self.cost_budget, self.spent
        # a budget limit of 0 means "unlimited"; remaining is reported as 0 in that case
        remaining = CostRecord(
            tokens=max(b.max_tokens - s.tokens, 0) if b.max_tokens else 0,
            api_cost_usd=max(b.max_api_cost_usd - s.api_cost_usd, 0.0) if b.max_api_cost_usd else 0.0,
            execution_time_seconds=(
                max(b.max_wall_time_seconds - s.execution_time_seconds, 0.0) if b.max_wall_time_seconds else 0.0
            ),
            verification_cost=(
                max(b.max_verification_cost - s.verification_cost, 0.0) if b.max_verification_cost else 0.0
            ),
        )
        return BudgetState(
            attempt_count=self.attempts, max_attempts=self.retry_budget.max_attempts,
            spent=CostRecord(**vars(s)), remaining=remaining,
        )

    def exhausted(self) -> bool:
        b, s = self.cost_budget, self.spent
        return any([
            b.max_tokens and s.tokens >= b.max_tokens,
            b.max_api_cost_usd and s.api_cost_usd >= b.max_api_cost_usd,
            b.max_wall_time_seconds and s.execution_time_seconds >= b.max_wall_time_seconds,
            b.max_verification_cost and s.verification_cost >= b.max_verification_cost,
        ])

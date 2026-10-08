from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CostRecord:
    tokens: int = 0
    api_cost_usd: float = 0.0
    execution_time_seconds: float = 0.0
    verification_cost: float = 0.0


@dataclass
class BudgetState:
    """Snapshot of progress and remaining budget, input to adaptive control."""

    attempt_count: int = 0
    max_attempts: int = 0
    spent: CostRecord = field(default_factory=CostRecord)
    remaining: CostRecord = field(default_factory=CostRecord)
    confidence: float = 0.0
    expected_improvement: float = 0.0

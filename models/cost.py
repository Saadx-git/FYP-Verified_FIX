from __future__ import annotations

from dataclasses import dataclass


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
    spent: CostRecord = None  # TODO: default to CostRecord()
    remaining: CostRecord = None  # TODO: default to CostRecord()
    confidence: float = 0.0
    expected_improvement: float = 0.0

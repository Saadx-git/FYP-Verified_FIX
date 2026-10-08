from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metrics:
    n_instances: int = 0
    issue_resolution_rate: float = 0.0
    patch_correctness: float = 0.0
    regression_rate: float = 0.0
    verification_accuracy: float = 0.0
    false_acceptance_rate: float = 0.0
    false_rejection_rate: float = 0.0
    repair_success_after_feedback: float = 0.0
    verification_cost: float = 0.0
    repair_efficiency: float = 0.0
    execution_time_seconds: float = 0.0
    token_api_usage: int = 0

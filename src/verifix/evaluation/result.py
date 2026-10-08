from __future__ import annotations

from dataclasses import dataclass, field

from verifix.evaluation.metrics import Metrics


@dataclass
class EvaluationResult:
    experiment_name: str = ""
    metrics: Metrics = field(default_factory=Metrics)
    per_instance: dict = field(default_factory=dict)

from __future__ import annotations

from verifix.evaluation.experiment import Experiment, load_instances
from verifix.evaluation.result import EvaluationResult


class BenchmarkRunner:
    """Runs experiments over a benchmark dataset (a JSON list of instances)."""

    def run(self, experiment: Experiment, dataset_path: str) -> EvaluationResult:
        return experiment.run(load_instances(dataset_path))

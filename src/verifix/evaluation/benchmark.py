from __future__ import annotations

from verifix.evaluation.experiment import Experiment
from verifix.evaluation.result import EvaluationResult


class BenchmarkRunner:
    """Runs experiments over a benchmark dataset."""

    def run(self, experiment: Experiment, dataset_path: str) -> EvaluationResult:
        """TODO: Run the benchmark."""
        raise NotImplementedError

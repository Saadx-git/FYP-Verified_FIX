from __future__ import annotations

from verifix.evaluation.benchmark import BenchmarkRunner
from verifix.evaluation.experiment import Experiment
from verifix.evaluation.result import EvaluationResult


class AblationStudy:
    """Runs experiments with components removed, over one dataset."""

    def __init__(self, experiments: list[Experiment], dataset_path: str = "") -> None:
        self.experiments = experiments
        self.dataset_path = dataset_path

    def run(self) -> list[EvaluationResult]:
        return [BenchmarkRunner().run(e, self.dataset_path) for e in self.experiments]

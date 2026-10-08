from __future__ import annotations

from verifix.evaluation.experiment import Experiment
from verifix.evaluation.result import EvaluationResult


class AblationStudy:
    """Runs experiments with components removed."""

    def __init__(self, experiments: list[Experiment]) -> None:
        self.experiments = experiments

    def run(self) -> list[EvaluationResult]:
        """TODO: Run the ablation study."""
        raise NotImplementedError

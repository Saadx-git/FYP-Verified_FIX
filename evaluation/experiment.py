from __future__ import annotations

from dataclasses import dataclass, field

from verifix.config.models import VerifixConfig
from verifix.evaluation.result import EvaluationResult


@dataclass
class Experiment:
    name: str = ""
    config: VerifixConfig = field(default_factory=VerifixConfig)

    def run(self) -> EvaluationResult:
        """TODO: Run the experiment."""
        raise NotImplementedError

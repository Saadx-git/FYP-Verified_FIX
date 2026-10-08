from __future__ import annotations

from verifix.evaluation.experiment import Experiment


class Baseline(Experiment):
    """A comparison configuration (e.g. agent without verification)."""

    def run(self):
        """TODO: Run the baseline."""
        raise NotImplementedError

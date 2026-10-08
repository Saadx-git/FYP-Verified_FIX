from __future__ import annotations

from dataclasses import replace

from verifix.evaluation.experiment import AgentFactory, Experiment
from verifix.factory import ALL_VERIFIERS, HarnessOptions

_RAW = {"feedback": "raw", "adaptive_verification": False, "adaptive_stopping": False, "adaptive_repair": False}


class Baseline(Experiment):
    """A comparison configuration (e.g. agent without verification)."""


def configurations(max_attempts: int = 3) -> dict[str, HarnessOptions]:
    """Baselines A-C, the full system and ablations A-F (proposal sections 9.6 and 13.2)."""
    full = HarnessOptions(max_attempts=max_attempts)
    return {
        "baseline-a": HarnessOptions(verifiers=[], max_attempts=1, required=set(), **_RAW),
        "baseline-b": HarnessOptions(verifiers=["unit_tests"], max_attempts=max_attempts, **_RAW),
        "baseline-c": HarnessOptions(verifiers=list(ALL_VERIFIERS), max_attempts=max_attempts, **_RAW),
        "full": full,
        "ablation-a": replace(full, fusion="tests_only"),                       # no evidence fusion
        "ablation-b": replace(full, feedback="raw"),                            # no failure diagnosis
        "ablation-c": replace(full, adaptive_verification=False),               # no adaptive verification
        "ablation-d": replace(full, adaptive_repair=False),                     # no adaptive repair selection
        "ablation-e": replace(full, adaptive_stopping=False),                   # no cost-aware stopping
        "ablation-f": replace(full, verifiers=[v for v in ALL_VERIFIERS if v != "requirement"]),  # no requirement check
    }


def make_experiment(name: str, agent_factory: AgentFactory, max_attempts: int = 3, client=None) -> Experiment:
    return Experiment(name=name, options=configurations(max_attempts)[name], agent_factory=agent_factory, client=client)

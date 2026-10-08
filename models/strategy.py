from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RepairStrategyType(Enum):
    REVISE_PATCH = "revise_patch"
    REGENERATE_PATCH = "regenerate_patch"
    REEXPLORE_REPOSITORY = "reexplore_repository"
    FIX_ENVIRONMENT = "fix_environment"


@dataclass
class RepairStrategy:
    strategy_type: RepairStrategyType = RepairStrategyType.REVISE_PATCH
    parameters: dict = field(default_factory=dict)


@dataclass
class VerificationStrategy:
    """Which verifiers to run next, and in what order."""

    verifier_names: list[str] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)

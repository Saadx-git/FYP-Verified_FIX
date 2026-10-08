from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChangeType(Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class ChangedFile:
    path: str = ""
    change_type: ChangeType = ChangeType.MODIFIED
    diff: str = ""


@dataclass
class PatchMetadata:
    attempt: int = 0
    agent_name: str = ""
    agent_confidence: float = 0.0
    tokens_used: int = 0
    generation_time_seconds: float = 0.0


@dataclass
class RepairPlan:
    summary: str = ""
    steps: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)


@dataclass
class CandidatePatch:
    patch_id: str = ""
    diff: str = ""
    plan: RepairPlan = field(default_factory=RepairPlan)
    changed_files: list[ChangedFile] = field(default_factory=list)
    metadata: PatchMetadata = field(default_factory=PatchMetadata)

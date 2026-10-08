from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from verifix.models.failure import TargetedFeedback
from verifix.models.issue import Issue
from verifix.models.patch import CandidatePatch, RepairPlan


@dataclass
class AgentRequest:
    issue: Issue = None  # TODO: required
    repo_path: str = ""
    feedback: TargetedFeedback | None = None
    context: dict = field(default_factory=dict)


@dataclass
class AgentResponse:
    patch: CandidatePatch | None = None
    plan: RepairPlan | None = None
    raw_output: str = ""


class CodingAgent(ABC):
    """Pluggable coding agent (e.g. SWE-agent, Aider)."""

    @abstractmethod
    def generate_patch(self, request: AgentRequest) -> AgentResponse:
        """TODO: Produce a candidate patch for the request."""
        raise NotImplementedError

from __future__ import annotations

from verifix.agent.base import AgentRequest
from verifix.agent.orchestrator import AgentOrchestrator
from verifix.models.patch import CandidatePatch


class PatchGenerator:
    """Responsible for producing candidate patches via the agent."""

    def __init__(self, agent_orchestrator: AgentOrchestrator) -> None:
        self.agent_orchestrator = agent_orchestrator

    def generate(self, request: AgentRequest) -> CandidatePatch:
        """TODO: Generate a candidate patch."""
        raise NotImplementedError

from __future__ import annotations

from verifix.agent.base import AgentRequest, AgentResponse, CodingAgent


class AgentOrchestrator:
    """Drives the agent action step of the pipeline."""

    def __init__(self, agent: CodingAgent) -> None:
        self.agent = agent

    def run_agent(self, request: AgentRequest) -> AgentResponse:
        """TODO: Invoke the agent and return its response."""
        raise NotImplementedError

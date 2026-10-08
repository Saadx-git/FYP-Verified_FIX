from __future__ import annotations

import time

from verifix.agent.base import AgentRequest, AgentResponse, CodingAgent


class AgentOrchestrator:
    """Drives the agent action step of the pipeline."""

    def __init__(self, agent: CodingAgent) -> None:
        self.agent = agent

    def run_agent(self, request: AgentRequest) -> AgentResponse:
        start = time.monotonic()
        response = self.agent.generate_patch(request)
        if response.patch:
            response.patch.metadata.generation_time_seconds = time.monotonic() - start
        return response

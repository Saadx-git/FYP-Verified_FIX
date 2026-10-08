from __future__ import annotations

from verifix.agent.base import AgentRequest
from verifix.agent.orchestrator import AgentOrchestrator
from verifix.models.patch import CandidatePatch
from verifix.patching.diff import parse_changed_files


class PatchGenerator:
    """Responsible for producing candidate patches via the agent."""

    def __init__(self, agent_orchestrator: AgentOrchestrator) -> None:
        self.agent_orchestrator = agent_orchestrator
        self._count = 0

    def generate(self, request: AgentRequest) -> CandidatePatch:
        response = self.agent_orchestrator.run_agent(request)
        patch = response.patch or CandidatePatch()
        self._count += 1
        patch.patch_id = patch.patch_id or f"patch-{self._count}"
        patch.metadata.attempt = self._count
        if response.plan and not patch.plan.summary:
            patch.plan = response.plan
        if not patch.changed_files:
            patch.changed_files = parse_changed_files(patch.diff)
        return patch

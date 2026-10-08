from __future__ import annotations

from pathlib import Path

from verifix.agent.base import AgentRequest, AgentResponse, CodingAgent
from verifix.models.patch import CandidatePatch, PatchMetadata, RepairPlan


class FakeAgent(CodingAgent):
    """Replays canned diffs (one per attempt); for tests and demos without an LLM."""

    def __init__(self, diffs: list[str]) -> None:
        self.diffs = diffs
        self.calls = 0
        self.requests: list[AgentRequest] = []  # what the harness asked for, per attempt (tests inspect this)

    @classmethod
    def from_dir(cls, directory: str) -> FakeAgent:
        return cls([p.read_text() for p in sorted(Path(directory).glob("*.diff"))])

    def generate_patch(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        diff = self.diffs[min(self.calls, len(self.diffs) - 1)] if self.diffs else ""
        self.calls += 1
        note = f" (feedback: {request.feedback.summary})" if request.feedback else ""
        plan = RepairPlan(summary=f"canned attempt {self.calls}{note}", target_files=[request.issue.target_file])
        return AgentResponse(
            patch=CandidatePatch(diff=diff, plan=plan, metadata=PatchMetadata(agent_name="fake", agent_confidence=0.5)),
            plan=plan, raw_output=diff,
        )

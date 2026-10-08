from __future__ import annotations

from dataclasses import dataclass, field

from verifix.models.cost import CostRecord
from verifix.models.evidence import PatchAssessment, VerificationDecision
from verifix.models.patch import CandidatePatch


@dataclass
class VerificationReport:
    issue_id: str = ""
    final_patch: CandidatePatch | None = None
    decision: VerificationDecision | None = None
    assessments: list[PatchAssessment] = field(default_factory=list)
    attempts: int = 0
    cost: CostRecord = field(default_factory=CostRecord)
    history: list[dict] = field(default_factory=list)  # one entry per attempt: diff, plan, decision, diagnosis

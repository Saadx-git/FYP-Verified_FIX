from __future__ import annotations

from verifix.models.evidence import PatchAssessment
from verifix.models.patch import CandidatePatch


class PatchRanker:
    """Responsible for ranking candidate patches."""

    def rank(
        self,
        patches: list[CandidatePatch],
        assessments: list[PatchAssessment],
    ) -> list[CandidatePatch]:
        """TODO: Order patches best-first."""
        raise NotImplementedError

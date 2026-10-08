from __future__ import annotations

from verifix.models.evidence import PatchAssessment, VerificationStatus
from verifix.models.patch import CandidatePatch


def _changed_lines(patch: CandidatePatch) -> int:
    return sum(1 for ln in patch.diff.splitlines() if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")))


class PatchRanker:
    """Orders candidate patches best-first: fewest failed verifiers, then highest reliability,
    then smallest change (less regression risk)."""

    def rank(self, patches: list[CandidatePatch], assessments: list[PatchAssessment]) -> list[CandidatePatch]:
        by_id = {a.patch_id: a for a in assessments}

        def key(p: CandidatePatch) -> tuple[int, float, int]:
            a = by_id.get(p.patch_id)
            fails = sum(r.status is VerificationStatus.FAIL for r in a.results) if a else 99
            return (fails, -(a.reliability_score if a else 0.0), _changed_lines(p))

        return sorted(patches, key=key)

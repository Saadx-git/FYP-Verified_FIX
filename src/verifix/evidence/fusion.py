from __future__ import annotations

from verifix.models.evidence import (
    DecisionType,
    PatchAssessment,
    VerificationDecision,
    VerificationResult,
    VerificationStatus,
)

_SCORE = {
    VerificationStatus.PASS: 1.0,
    VerificationStatus.WARNING: 0.6,
    VerificationStatus.UNCERTAIN: 0.4,
    VerificationStatus.FAIL: 0.0,
}
_DEFAULT_WEIGHTS = {
    "unit_tests": 3.0, "integration_tests": 2.0, "requirement": 2.5,
    "security": 2.0, "static_analysis": 1.0, "llm_review": 1.0, "mutation": 0.5,
}


class EvidenceFusionEngine:
    """Interprets collected evidence into an assessment and a decision (rule-based)."""

    def __init__(self, required: set[str] | None = None, weights: dict[str, float] | None = None,
                 decide_on: set[str] | None = None) -> None:
        self.decide_on = decide_on  # restrict the decision to these verifiers (None = use all evidence)
        self.required = required if required is not None else {"unit_tests"}
        self.weights = weights or _DEFAULT_WEIGHTS

    def fuse(self, patch_id: str, results: list[VerificationResult]) -> PatchAssessment:
        scored = [r for r in results if r.status is not VerificationStatus.NOT_RUN]
        total = sum(self.weights.get(r.verifier_name, 1.0) for r in scored)
        score = (
            sum(self.weights.get(r.verifier_name, 1.0) * _SCORE[r.status] * max(r.confidence, 0.0)
                for r in scored) / total
            if total else 0.0
        )
        return PatchAssessment(patch_id=patch_id, reliability_score=round(score, 3), results=results)

    def decide(self, assessment: PatchAssessment) -> VerificationDecision:
        by_name = {r.verifier_name: r for r in assessment.results
                   if self.decide_on is None or r.verifier_name in self.decide_on}
        failed = [n for n, r in by_name.items() if r.status is VerificationStatus.FAIL]
        if failed:
            return VerificationDecision(
                DecisionType.REPAIR_REQUIRED, assessment, f"failed: {', '.join(sorted(failed))}"
            )
        missing = [n for n in self.required
                   if n not in by_name or by_name[n].status in (VerificationStatus.NOT_RUN, VerificationStatus.UNCERTAIN)]
        if missing:
            return VerificationDecision(
                DecisionType.INSUFFICIENT_EVIDENCE, assessment, f"no conclusive evidence: {', '.join(sorted(missing))}"
            )
        return VerificationDecision(DecisionType.VERIFIED, assessment, "all required evidence passed")

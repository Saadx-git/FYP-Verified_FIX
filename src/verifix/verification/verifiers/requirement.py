from __future__ import annotations

from verifix.llm.client import GroqClient
from verifix.models.evidence import VerificationFinding, VerificationResult, VerificationStatus
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers._llm import MAX_DIFF, ask_json, issue_text, prior_text

SYSTEM = (
    "You are an independent verifier. Decide whether a code patch satisfies each requirement of a bug report. "
    "Judge only from the issue, the planned intent, the diff and the test outcomes. Be strict but fair: mark a "
    "requirement 'met' only if the diff clearly implements it, 'not_met' only if you can point to a concrete gap, "
    "otherwise 'unclear'. Respond with JSON: "
    '{"requirements":[{"id":str,"status":"met"|"not_met"|"unclear","reason":str}]}'
)


class RequirementVerifier(Verifier):
    """Checks reported requirement -> planned intent -> actual patch -> observed test behaviour."""

    name = "requirement"

    def __init__(self, client: GroqClient, model: str) -> None:
        self.client, self.model = client, model

    def verify(self, context: VerificationContext) -> VerificationResult:
        issue = context.issue
        reqs = "\n".join(f"- {r.id}: {r.description}. Observed: {r.observed_behavior}. Expected: {r.expected_behavior}"
                         for r in issue.requirements) or "- R1: the issue is resolved as described"
        user = (f"{issue_text(context)}\n\nRequirements:\n{reqs}\n\nPlanned intent: {context.patch.plan.summary}\n\n"
                f"Test/analysis outcomes:\n{prior_text(context)}\n\nDiff:\n{context.patch.diff[:MAX_DIFF]}")
        data, tokens = ask_json(self.client, self.model, SYSTEM, user)
        verdicts = [v for v in data.get("requirements", []) if isinstance(v, dict)]
        if not verdicts:
            return VerificationResult(self.name, VerificationStatus.UNCERTAIN, 0.0,
                                      [VerificationFinding("verifier returned no usable verdicts", "warning")], cost=tokens)
        findings = [VerificationFinding(f"{v.get('id', '?')} {v.get('status', '?')}: {v.get('reason', '')}"[:300],
                                        "error" if v.get("status") == "not_met" else "info") for v in verdicts]
        statuses = {v.get("status") for v in verdicts}
        status = (VerificationStatus.FAIL if "not_met" in statuses else
                  VerificationStatus.UNCERTAIN if "unclear" in statuses else VerificationStatus.PASS)
        return VerificationResult(self.name, status, 0.8, findings, cost=tokens)

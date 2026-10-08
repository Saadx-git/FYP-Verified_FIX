from __future__ import annotations

from verifix.llm.client import GroqClient
from verifix.models.evidence import VerificationFinding, VerificationResult, VerificationStatus
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers._llm import MAX_DIFF, ask_json, issue_text

SYSTEM = (
    "You are a senior code reviewer who did NOT write this patch. Review the diff for correctness against the issue, "
    "missed edge cases, regressions, and security problems. Do not praise. "
    'Respond with JSON: {"verdict":"approve"|"concerns"|"reject","concerns":[str]}'
)


class LLMReviewVerifier(Verifier):
    """Independent LLM review. Sees only issue + diff (never the agent's reasoning); advisory, never blocks alone."""

    name = "llm_review"

    def __init__(self, client: GroqClient, model: str) -> None:
        self.client, self.model = client, model

    def verify(self, context: VerificationContext) -> VerificationResult:
        data, tokens = ask_json(self.client, self.model, SYSTEM,
                                f"{issue_text(context)}\n\nDiff:\n{context.patch.diff[:MAX_DIFF]}")
        verdict = data.get("verdict")
        concerns = [str(c)[:240] for c in data.get("concerns", [])][:6]
        if verdict not in ("approve", "concerns", "reject"):
            return VerificationResult(self.name, VerificationStatus.UNCERTAIN, 0.0,
                                      [VerificationFinding("review returned no usable verdict", "warning")], cost=tokens)
        if verdict == "approve":
            return VerificationResult(self.name, VerificationStatus.PASS, 0.7,
                                      [VerificationFinding("reviewer approved", "info")], cost=tokens)
        # advisory: a reviewer's objections lower the score and feed the diagnosis but cannot veto tests alone
        return VerificationResult(self.name, VerificationStatus.WARNING, 0.7,
                                  [VerificationFinding(c, "warning") for c in concerns] or [VerificationFinding(verdict, "warning")],
                                  cost=tokens)

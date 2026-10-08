from __future__ import annotations

from verifix.models.evidence import VerificationFinding, VerificationResult, VerificationStatus
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers._delta import Finding, loads, new_findings


def _argv(files: list[str]) -> list[str]:
    return ["bandit", "-q", "-f", "json", *files]


def _parse(text: str) -> list[Finding]:
    data = loads(text)
    results = data.get("results", []) if isinstance(data, dict) else []
    return [
        (r["test_id"], r["issue_severity"].lower(), r["issue_text"], f"{r['filename']}:{r['line_number']}")
        for r in results
    ]


class SecurityVerifier(Verifier):
    """Bandit on changed files; new MEDIUM/HIGH findings block the patch."""

    name = "security"

    def verify(self, context: VerificationContext) -> VerificationResult:
        fresh = new_findings(context, _argv, _parse)
        if not fresh:
            return VerificationResult(self.name, VerificationStatus.PASS, 1.0, [VerificationFinding("no new security findings", "info")])
        blocking = any(sev in ("medium", "high") for _, sev, _, _ in fresh)
        findings = [VerificationFinding(f"{r}: {m}", sev, loc) for r, sev, m, loc in fresh]
        return VerificationResult(self.name, VerificationStatus.FAIL if blocking else VerificationStatus.WARNING, 0.9, findings)

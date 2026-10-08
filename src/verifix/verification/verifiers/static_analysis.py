from __future__ import annotations

from verifix.models.evidence import VerificationFinding, VerificationResult, VerificationStatus
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.verifiers._delta import Finding, loads, new_findings

_BLOCKING = ("F821", "F822", "F823", "F63", "F7", "E9")  # undefined names, syntax errors


def _argv(files: list[str]) -> list[str]:
    return ["ruff", "check", "--isolated", "--no-cache", "--select", "E9,F,B", "--output-format", "json", *files]


def _parse(text: str) -> list[Finding]:
    return [
        (d.get("code") or "", "error", d.get("message", ""), f"{d.get('filename', '')}:{d.get('location', {}).get('row', 0)}")
        for d in loads(text) if isinstance(d, dict)
    ]


class StaticAnalysisVerifier(Verifier):
    """ruff on changed files; only findings introduced by the patch count."""

    name = "static_analysis"

    def verify(self, context: VerificationContext) -> VerificationResult:
        fresh = new_findings(context, _argv, _parse)
        if not fresh:
            return VerificationResult(self.name, VerificationStatus.PASS, 1.0, [VerificationFinding("no new findings", "info")])
        status = VerificationStatus.FAIL if any(f[0].startswith(_BLOCKING) for f in fresh) else VerificationStatus.WARNING
        findings = [VerificationFinding(f"{r}: {m}", sev, loc) for r, sev, m, loc in fresh]
        return VerificationResult(self.name, status, 0.9, findings)

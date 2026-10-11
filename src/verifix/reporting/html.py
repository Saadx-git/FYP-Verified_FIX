from __future__ import annotations

import html
import json

from verifix.reporting.generator import ReportGenerator
from verifix.reporting.report import VerificationReport

_CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1f2328;--mut:#656d76;--bd:#d0d7de;--ok:#1a7f37;--bad:#cf222e;--warn:#9a6700;--add:#dafbe1;--del:#ffebe9;--card:#f6f8fa}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--bd:#30363d;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--add:#12261e;--del:#2d1214;--card:#161b22}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:auto}h1{font-size:20px;margin:0 0 4px}h2{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:28px 0 8px}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-weight:600;font-size:12px;border:1px solid currentColor}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.mut{color:var(--mut)}
table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--bd);padding:6px 10px;text-align:left;vertical-align:top;font-size:13px}th{background:var(--card)}
.card{border:1px solid var(--bd);border-radius:6px;padding:12px 14px;margin:10px 0;background:var(--card)}
pre{margin:0;overflow-x:auto;font:12px/1.45 ui-monospace,monospace;border:1px solid var(--bd);border-radius:6px;background:var(--bg)}
pre div{padding:0 10px;white-space:pre}.add{background:var(--add)}.del{background:var(--del)}.hdr{color:var(--mut)}
details{margin:8px 0;border:1px solid var(--bd);border-radius:6px;background:var(--bg)}summary{cursor:pointer;padding:6px 10px;font-weight:600}details table{margin:0}details td pre{border:0;white-space:pre-wrap;max-height:180px;overflow:auto}.o-passed,.o-xpassed{color:var(--ok)}.o-failed,.o-error{color:var(--bad);font-weight:600}.o-xfailed{color:var(--warn)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}.grid .card{margin:0}.grid b{display:block;font-size:18px}
"""
_STATUS = {"pass": "ok", "fail": "bad", "warning": "warn", "uncertain": "warn", "not_run": "mut"}
_DECISION = {"verified": ("VERIFIED", "ok"), "reject": ("REJECTED", "bad"), "repair_required": ("REPAIR REQUIRED", "warn"),
             "insufficient_evidence": ("INSUFFICIENT EVIDENCE", "warn")}


def _e(x: object) -> str:
    return html.escape(str(x))


def _diff(diff: str) -> str:
    rows = []
    for line in diff.splitlines():
        if line.startswith(("diff --git", "index ", "--- ", "+++ ")):
            cls = "hdr"
        else:
            cls = "add" if line.startswith("+") else "del" if line.startswith("-") else "hdr" if line.startswith("@@") else ""
        rows.append(f'<div class="{cls}">{_e(line) or "&nbsp;"}</div>')
    return f"<pre>{''.join(rows)}</pre>" if rows else '<p class="mut">(empty diff)</p>'


def _tests(result) -> str:
    """Collapsible per-test table for one verifier run (failures first, open when something failed)."""
    if not result.tests:
        return ""
    bad = [t for t in result.tests if t.outcome in ("failed", "error")]
    counts = ", ".join(f"{sum(t.outcome == o for t in result.tests)} {o}" for o in dict.fromkeys(t.outcome for t in result.tests))
    rows = "".join(
        f'<tr><td>{_e(t.test_id)}</td><td>{_e(t.role)}</td><td class="o-{_e(t.outcome)}">{_e(t.outcome)}</td>'
        f"<td>{'' if t.duration is None else f'{t.duration:.3f}s'}</td>"
        f"<td>{'<pre>' + _e(t.message) + '</pre>' if t.message else ''}</td></tr>" for t in result.tests)
    return (f"<details{' open' if bad else ''}><summary>{_e(result.verifier_name)} tests: {counts}</summary>"
            f"<table><tr><th>Test</th><th>Role</th><th>Outcome</th><th>Time</th><th>Details</th></tr>{rows}</table></details>")


class HTMLReportGenerator(ReportGenerator):
    """Self-contained, shareable verification report (no external assets)."""

    def generate(self, report: VerificationReport) -> str:
        d = report.decision
        label, cls = _DECISION.get(d.decision.value if d else "", ("NO DECISION", "mut"))
        out = [("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>Verifix report — {_e(report.issue_id)}</title><style>{_CSS}</style><main>"),
               f"<h1>Verifix report — issue {_e(report.issue_id)}</h1>",
               (f'<span class="badge {cls}">{label}</span> <span class="mut">after {report.attempts} attempt(s)'
                f"{' — ' + _e(d.rationale) if d else ''}</span>"),
               '<div class="grid" style="margin-top:14px">',
               f'<div class="card">Reliability<b>{d.assessment.reliability_score if d else 0}</b></div>',
               f'<div class="card">Attempts<b>{report.attempts}</b></div>',
               f'<div class="card">Tokens<b>{report.cost.tokens}</b></div>',
               f'<div class="card">Time<b>{report.cost.execution_time_seconds:.1f}s</b></div></div>']
        if d:
            out.append("<h2>Final evidence</h2><table><tr><th>Verifier</th><th>Status</th><th>Confidence</th><th>Findings</th></tr>")
            for r in d.assessment.results:
                findings = "<br>".join(_e(f.message) for f in r.findings[:6]) or "—"
                out.append(f'<tr><td>{_e(r.verifier_name)}</td><td class="{_STATUS.get(r.status.value, "mut")}">{_e(r.status.value)}</td>'
                           f"<td>{r.confidence:.2f}</td><td>{findings}</td></tr>")
            out.append("</table>")
        out.append("<h2>Attempt history</h2>")
        for i, h in enumerate(report.history):
            lab, c = _DECISION.get(h["decision"], (h["decision"], "mut"))
            diag = h.get("diagnosis")
            out.append(f'<div class="card"><b>Attempt {h["attempt"]}</b> <span class="badge {c}">{lab}</span> '
                       f'<span class="mut">score {h["score"]}</span><p class="mut">{_e(h["plan"])}</p>')
            if diag:
                out.append(f'<p><b>Diagnosis:</b> {_e(diag["category"])} &rarr; strategy <code>{_e(diag["strategy"])}</code><br>'
                           f'<span class="mut">{_e(diag["summary"])}</span></p>')
            out.append(_diff(h["diff"]))
            if i < len(report.assessments):
                out.extend(_tests(r) for r in report.assessments[i].results)
            out.append("</div>")
        if report.final_patch:
            out.append("<h2>Final patch</h2>" + _diff(report.final_patch.diff))
        out.append("<p class=mut>Evidence-based assessment; a VERIFIED result does not prove absolute correctness.</p></main>")
        return "".join(out)


def report_from_json(text: str) -> VerificationReport:
    """Rebuild a report from its saved JSON (inverse of JSONReportGenerator)."""
    from verifix.models.cost import CostRecord
    from verifix.models.evidence import (
        DecisionType,
        PatchAssessment,
        TestOutcome,
        VerificationDecision,
        VerificationFinding,
        VerificationResult,
        VerificationStatus,
    )
    from verifix.models.patch import CandidatePatch

    raw = json.loads(text)

    def result(r: dict) -> VerificationResult:
        return VerificationResult(r["verifier_name"], VerificationStatus(r["status"]), r["confidence"],
                                  [VerificationFinding(**f) for f in r["findings"]], [], r["cost"], r["duration_seconds"],
                                  [TestOutcome(**t) for t in r.get("tests", [])])

    def assessment(a: dict) -> PatchAssessment:
        return PatchAssessment(a["patch_id"], a["reliability_score"], [result(r) for r in a["results"]])

    dec = raw.get("decision")
    patch = raw.get("final_patch")
    return VerificationReport(
        issue_id=raw["issue_id"], attempts=raw["attempts"], history=raw.get("history", []),
        final_patch=CandidatePatch(patch_id=patch["patch_id"], diff=patch["diff"]) if patch else None,
        decision=VerificationDecision(DecisionType(dec["decision"]), assessment(dec["assessment"]), dec["rationale"]) if dec else None,
        assessments=[assessment(a) for a in raw.get("assessments", [])], cost=CostRecord(**raw.get("cost", {})),
    )

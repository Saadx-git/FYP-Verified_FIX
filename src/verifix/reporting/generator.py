from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from enum import Enum

from verifix.reporting.report import VerificationReport


class ReportGenerator(ABC):
    @abstractmethod
    def generate(self, report: VerificationReport) -> str:
        """Render the report."""
        raise NotImplementedError


def _plain(obj):
    return obj.value if isinstance(obj, Enum) else str(obj)


class JSONReportGenerator(ReportGenerator):
    def generate(self, report: VerificationReport) -> str:
        return json.dumps(asdict(report), default=_plain, indent=2)


class HumanReadableReportGenerator(ReportGenerator):
    def generate(self, report: VerificationReport) -> str:
        d = report.decision
        lines = [f"Issue {report.issue_id}: {d.decision.value.upper() if d else 'NO DECISION'} after {report.attempts} attempt(s)"]
        if d:
            lines.append(f"  rationale: {d.rationale}")
            for r in d.assessment.results:
                lines.append(f"  - {r.verifier_name}: {r.status.value} ({'; '.join(f.message for f in r.findings[:2])})")
        return "\n".join(lines)

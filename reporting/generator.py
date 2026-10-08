from __future__ import annotations

from abc import ABC, abstractmethod

from verifix.reporting.report import VerificationReport


class ReportGenerator(ABC):
    @abstractmethod
    def generate(self, report: VerificationReport) -> str:
        """TODO: Render the report."""
        raise NotImplementedError


class JSONReportGenerator(ReportGenerator):
    def generate(self, report: VerificationReport) -> str:
        """TODO: Render as JSON."""
        raise NotImplementedError


class HumanReadableReportGenerator(ReportGenerator):
    def generate(self, report: VerificationReport) -> str:
        """TODO: Render as human-readable text."""
        raise NotImplementedError

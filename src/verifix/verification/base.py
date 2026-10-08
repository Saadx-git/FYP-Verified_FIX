from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from verifix.models.evidence import VerificationResult
from verifix.models.issue import Issue
from verifix.models.patch import CandidatePatch
from verifix.sandbox.base import ExecutionSandbox


@dataclass
class VerificationContext:
    """Everything a verifier may need."""

    issue: Issue = field(default_factory=Issue)
    patch: CandidatePatch = field(default_factory=CandidatePatch)
    repo_path: str = ""
    sandbox: ExecutionSandbox | None = None
    extra: dict = field(default_factory=dict)


class Verifier(ABC):
    """Common interface for all verification mechanisms."""

    name: str = ""

    @abstractmethod
    def verify(self, context: VerificationContext) -> VerificationResult:
        """TODO: Run this verification mechanism."""
        raise NotImplementedError

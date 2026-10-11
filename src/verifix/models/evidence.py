from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VerificationStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    UNCERTAIN = "uncertain"
    NOT_RUN = "not_run"


class DecisionType(Enum):
    VERIFIED = "verified"
    REPAIR_REQUIRED = "repair_required"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REJECT = "reject"


@dataclass
class VerificationFinding:
    """A single issue/observation reported by a verifier."""

    message: str = ""
    severity: str = ""
    location: str = ""


@dataclass
class Evidence:
    """A piece of raw evidence produced by a verifier."""

    source: str = ""
    kind: str = ""
    content: Any = None


@dataclass
class TestOutcome:
    """One test's result in a verifier run (kept so reports can show exactly what ran)."""

    __test__ = False  # not a pytest test class

    test_id: str = ""
    outcome: str = ""     # passed | failed | error | xfailed | xpassed
    role: str = ""        # fail_to_pass | pass_to_pass | reproduction | other
    duration: float | None = None
    message: str = ""     # failures only


@dataclass
class VerificationResult:
    """Output of one verifier run."""

    verifier_name: str = ""
    status: VerificationStatus = VerificationStatus.NOT_RUN
    confidence: float = 0.0
    findings: list[VerificationFinding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    cost: float = 0.0
    duration_seconds: float = 0.0
    tests: list[TestOutcome] = field(default_factory=list)


@dataclass
class PatchAssessment:
    """Fused interpretation of all evidence for a patch."""

    patch_id: str = ""
    reliability_score: float = 0.0
    results: list[VerificationResult] = field(default_factory=list)


@dataclass
class VerificationDecision:
    decision: DecisionType = DecisionType.INSUFFICIENT_EVIDENCE
    assessment: PatchAssessment = field(default_factory=PatchAssessment)
    rationale: str = ""

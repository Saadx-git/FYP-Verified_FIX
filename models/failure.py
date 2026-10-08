from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FailureCategory(Enum):
    ORIGINAL_BUG_UNRESOLVED = "original_bug_unresolved"
    REGRESSION_INTRODUCED = "regression_introduced"
    INCORRECT_IMPLEMENTATION = "incorrect_implementation"
    REQUIREMENT_MISMATCH = "requirement_mismatch"
    SECURITY_VIOLATION = "security_violation"
    TEST_ENVIRONMENT_FAILURE = "test_environment_failure"
    DEPENDENCY_CONFIGURATION_ISSUE = "dependency_configuration_issue"
    INSUFFICIENT_TEST_COVERAGE = "insufficient_test_coverage"


@dataclass
class RootCauseHypothesis:
    description: str = ""
    suspected_files: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class FailureDiagnosis:
    category: FailureCategory = FailureCategory.ORIGINAL_BUG_UNRESOLVED
    hypotheses: list[RootCauseHypothesis] = field(default_factory=list)


@dataclass
class TargetedFeedback:
    summary: str = ""
    details: list[str] = field(default_factory=list)
    suspected_files: list[str] = field(default_factory=list)

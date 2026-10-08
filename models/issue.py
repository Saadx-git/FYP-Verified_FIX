from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IssueRequirement:
    """A single requirement derived from an issue."""

    id: str = ""
    description: str = ""
    observed_behavior: str = ""
    expected_behavior: str = ""


@dataclass
class Issue:
    """A GitHub issue / bug report."""

    issue_id: str = ""
    repo: str = ""
    title: str = ""
    body: str = ""
    requirements: list[IssueRequirement] = field(default_factory=list)

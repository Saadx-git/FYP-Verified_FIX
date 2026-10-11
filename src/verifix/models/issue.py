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
    acceptance_criteria: list[str] = field(default_factory=list)
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    test_command: list[str] = field(default_factory=list)
    unclear: str = ""  # set when the report does not match the repository: the question to ask the user

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from verifix.models.issue import Issue, IssueRequirement


def load_issue(repo_path: str, issue_ref: str) -> Issue:
    """Load an issue from a JSON file path, or `<repo>/.verifix/issues/<id>.json`."""
    path = Path(issue_ref)
    if not path.is_file():
        path = Path(repo_path) / ".verifix" / "issues" / f"{issue_ref}.json"
    if not path.is_file():
        raise FileNotFoundError(f"issue {issue_ref!r} not found (looked at {path})")
    data = json.loads(path.read_text())
    reqs = [IssueRequirement(**r) for r in data.pop("requirements", [])]
    data = {k: v for k, v in data.items() if k in {f.name for f in fields(Issue)}}  # ignore legacy keys such as target_file
    return Issue(repo=repo_path, requirements=reqs, **data)

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from verifix.events.emitter import EventEmitter
from verifix.issue.github import fetch_issue, looks_like_github_issue
from verifix.issue.understanding import IssueUnderstander
from verifix.models.issue import Issue


def _save(repo: str, issue: Issue) -> None:
    path = Path(repo) / ".verifix" / "issues" / f"{issue.issue_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(issue)
    data.pop("repo")
    path.write_text(json.dumps(data, indent=2))


def resolve_issue(repo: str, *, ref: str | None, description: str | None,
                  understander: IssueUnderstander, emitter: EventEmitter | None = None, transport=None) -> str:
    """Turn whatever the user gave us into a cached, structured issue; return its id.

    Accepts a saved issue id / JSON path (used as-is), a GitHub issue URL or '#N', or free text.
    Users never have to write the JSON themselves.
    """
    emitter = emitter or EventEmitter()
    if ref and (Path(ref).is_file() or (Path(repo) / ".verifix" / "issues" / f"{ref}.json").is_file()
                or not looks_like_github_issue(ref)):
        return ref  # saved issue id or path to an existing JSON file (wins over a bare number like '142')
    if ref:
        emitter.emit("understanding_issue", source="github", ref=ref)
        number, title, body = fetch_issue(ref, repo, transport)
        issue_id, text = f"gh-{number}", f"{title}\n\n{body}"
    elif description and description.strip():
        emitter.emit("understanding_issue", source="text")
        title, text = "", description.strip()
        issue_id = "adhoc-" + hashlib.sha1(text.encode()).hexdigest()[:8]
    else:
        raise RuntimeError("provide --issue (id, URL or #N) or --description")
    _save(repo, understander.understand(issue_id, text, repo, title=title))
    return issue_id

from __future__ import annotations

import re

from verifix.llm.client import GroqClient
from verifix.models.issue import Issue, IssueRequirement
from verifix.repository.context_retriever import repo_outline
from verifix.verification.verifiers._llm import ask_json

SYSTEM = (
    "You turn a free-text bug report into a structured task for an automated repair system. "
    "Be faithful: never invent features, entities or behaviour that are not in the report or in the repository outline. "
    "Each requirement is one checkable behaviour. You are given an outline of the repository (files and top-level names): "
    "use the repository's real names, and if a word in the report looks like a typo of a name in the outline "
    "(for example 'Camp' for 'clamp'), use the real name. related_names lists the names, copied exactly from the outline, that "
    "the report is about; leave it empty if nothing in the outline is a plausible counterpart, and then put one short question "
    "for the reporter in clarification. "
    'Respond with JSON: {"related_names":[str],"clarification":str,"title":str,"requirements":[{"id":"R1",'
    '"description":str,"observed_behavior":str,"expected_behavior":str}],"acceptance_criteria":[str]}'
)


class IssueUnderstander:
    """Phase 1 / step 1 of the proposal: free text -> structured issue (requirements, criteria, likely file)."""

    def __init__(self, client: GroqClient, model: str) -> None:
        self.client, self.model = client, model

    def understand(self, issue_id: str, text: str, repo_path: str, title: str = "") -> Issue:
        outline = repo_outline(repo_path)
        data, _ = ask_json(self.client, self.model, SYSTEM, f"Repository outline:\n{outline}\n\nBug report:\n{text[:4000]}", "understand")
        # checked in code, not trusted: the report matches only if a name the model cites really is in the repository
        known = set(re.findall(r"\w+", outline))
        cited = [n for n in data.get("related_names", []) if isinstance(n, str) and n in known]
        unclear = "" if cited or not outline else str(data.get("clarification") or "Nothing in this repository matches the report.")
        reqs = [IssueRequirement(id=str(r.get("id") or f"R{i}"), description=str(r.get("description", "")),
                                 observed_behavior=str(r.get("observed_behavior", "")),
                                 expected_behavior=str(r.get("expected_behavior", "")))
                for i, r in enumerate(data.get("requirements", []), 1) if isinstance(r, dict)]
        first_line = text.strip().splitlines()[0][:100] if text.strip() else issue_id
        return Issue(
            issue_id=issue_id, repo=repo_path, title=title or str(data.get("title") or first_line), body=text,
            requirements=reqs, acceptance_criteria=[str(c) for c in data.get("acceptance_criteria", [])][:8], unclear=unclear,
        )

from __future__ import annotations

from verifix.models.issue import Issue


class ContextRetriever:
    """Responsible for retrieving code context relevant to an issue."""

    def retrieve(self, repo_path: str, issue: Issue) -> dict:
        """TODO: Retrieve relevant context."""
        raise NotImplementedError

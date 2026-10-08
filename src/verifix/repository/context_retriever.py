from __future__ import annotations

import re
from pathlib import Path

from verifix.models.issue import Issue
from verifix.repository.explorer import RepositoryExplorer
from verifix.repository.file_inspector import FileInspector
from verifix.repository.symbol_searcher import SymbolSearcher


class ContextRetriever:
    """Retrieves a small, relevant slice of the repo for an issue (keeps LLM context cheap)."""

    def retrieve(self, repo_path: str, issue: Issue) -> dict:
        files = RepositoryExplorer().list_files(repo_path)
        context: dict = {"files": files[:60]}
        if issue.target_file and Path(repo_path, issue.target_file).is_file():
            context["target_file"] = issue.target_file
            context["target_excerpt"] = FileInspector().read_file(str(Path(repo_path, issue.target_file)), max_lines=120)
        idents = {w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", f"{issue.title} {issue.body}") if "_" in w or w.islower()}
        symbols: list[str] = []
        for ident in sorted(idents)[:5]:
            symbols += SymbolSearcher().find_symbol(repo_path, ident)[:3]
        context["symbols"] = symbols[:10]
        return context

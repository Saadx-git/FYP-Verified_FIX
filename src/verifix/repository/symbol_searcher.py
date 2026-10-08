from __future__ import annotations

import ast
import re
from pathlib import Path

from verifix.repository.explorer import RepositoryExplorer


class SymbolSearcher:
    """Responsible for finding symbols (functions, classes) and text in a repository."""

    def find_symbol(self, repo_path: str, name: str) -> list[str]:
        """Definitions whose name contains `name`, as 'path:line: kind name'."""
        hits = []
        for rel in RepositoryExplorer().list_files(repo_path):
            if not rel.endswith(".py"):
                continue
            try:
                tree = ast.parse(Path(repo_path, rel).read_text(errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and name.lower() in node.name.lower():
                    hits.append(f"{rel}:{node.lineno}: {type(node).__name__.replace('Def', '').lower()} {node.name}")
        return hits

    def grep(self, repo_path: str, pattern: str, limit: int = 20) -> list[str]:
        rx = re.compile(pattern, re.IGNORECASE)
        hits = []
        for rel in RepositoryExplorer().list_files(repo_path):
            if not rel.endswith((".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json")):
                continue
            try:
                for i, line in enumerate(Path(repo_path, rel).read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{i}: {line.strip()[:160]}")
                        if len(hits) >= limit:
                            return hits
            except OSError:
                continue
        return hits

from __future__ import annotations


class SymbolSearcher:
    """Responsible for finding symbols (functions, classes) in a repository."""

    def find_symbol(self, repo_path: str, name: str) -> list[str]:
        """TODO: Locate symbol definitions/usages."""
        raise NotImplementedError

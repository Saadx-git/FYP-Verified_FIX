from __future__ import annotations

import ast
from pathlib import Path

from verifix.repository.explorer import RepositoryExplorer


class DependencyAnalyzer:
    """Builds a module-level import graph of the repository's own Python files."""

    def analyze(self, repo_path: str) -> dict[str, list[str]]:
        """Map each .py file to the repo files it imports (resolved by module path)."""
        files = [f for f in RepositoryExplorer().list_files(repo_path) if f.endswith(".py")]
        by_module = {self._module(f): f for f in files}
        graph: dict[str, list[str]] = {}
        for rel in files:
            try:
                tree = ast.parse(Path(repo_path, rel).read_text(errors="replace"))
            except SyntaxError:
                graph[rel] = []
                continue
            deps: set[str] = set()
            for node in ast.walk(tree):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                         [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
                         if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else [])
                for name in names:
                    # longest matching repo module wins (`pkg.mod.fn` -> pkg/mod.py)
                    parts = name.split(".")
                    for i in range(len(parts), 0, -1):
                        target = by_module.get(".".join(parts[:i]))
                        if target and target != rel:
                            deps.add(target)
                            break
            graph[rel] = sorted(deps)
        return graph

    def dependents(self, repo_path: str, rel_path: str) -> list[str]:
        """Files that import `rel_path`: where a change could cause regressions."""
        return sorted(f for f, deps in self.analyze(repo_path).items() if rel_path in deps)

    @staticmethod
    def _module(rel: str) -> str:
        mod = rel[:-3].replace("/", ".")
        return mod.removesuffix(".__init__")

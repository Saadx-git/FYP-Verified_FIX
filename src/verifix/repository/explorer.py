from __future__ import annotations

import os
import subprocess
from pathlib import Path

_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", ".verifix", ".pytest_cache"}


class RepositoryExplorer:
    """Responsible for navigating repository structure."""

    def list_files(self, repo_path: str) -> list[str]:
        tracked = subprocess.run(["git", "ls-files"], cwd=repo_path, capture_output=True, text=True, check=False)
        if tracked.returncode == 0 and tracked.stdout.strip():
            return tracked.stdout.split()
        out = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in _SKIP]
            out += [str(Path(root, f).relative_to(repo_path)) for f in files]
        return sorted(out)

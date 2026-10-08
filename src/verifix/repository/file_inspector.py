from __future__ import annotations

from pathlib import Path


class FileInspector:
    """Responsible for inspecting individual files."""

    def read_file(self, path: str, start: int = 1, end: int | None = None, max_lines: int = 200) -> str:
        """Return numbered lines [start, end], capped at max_lines to keep LLM context small."""
        lines = Path(path).read_text(errors="replace").splitlines()
        stop = min(end or len(lines), start - 1 + max_lines, len(lines))
        body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, stop + 1))
        more = f"\n... ({len(lines) - stop} more lines)" if stop < len(lines) else ""
        return body + more

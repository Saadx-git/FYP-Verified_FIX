from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from verifix.models.issue import Issue
from verifix.repository.explorer import RepositoryExplorer

_TRACEBACK = re.compile(r'File "(.+?\.py)", line (\d+)')
_BACKTICK = re.compile(r"`([^`\n]{2,80})`")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOP = {"the", "and", "for", "with", "this", "that", "from", "not", "are", "was", "when", "should", "returns", "return",
         "instead", "error", "none", "true", "false", "self", "def", "class", "import", "expected", "actual", "issue", "bug"}
_MAX_FILE_BYTES = 300_000
MAP_LIMIT = 2500
FULL_LISTING_UNDER = 80


class ContextRetriever:
    """Seeds the agent with where to start looking, without pinning the fix to one file.

    Clues come from the issue text (tracebacks, backticked code, identifiers, failing test names). The result is a
    repo map plus ranked candidate locations; no file contents are pre-loaded and the agent must still explore.
    """

    def retrieve(self, repo_path: str, issue: Issue) -> dict:
        files = RepositoryExplorer().list_files(repo_path)
        py_files = [f for f in files if f.endswith(".py")]
        text = f"{issue.title}\n{issue.body}\n" + " ".join(issue.fail_to_pass)
        score: Counter[str] = Counter()
        why: dict[str, tuple[int, str]] = {}  # file -> (line, reason) of the strongest clue

        def note(path: str, points: int, line: int, reason: str) -> None:
            score[path] += points
            if points >= score[path] - points or path not in why:
                why[path] = (line, reason)

        for m in _TRACEBACK.finditer(text):  # traceback frames name files outright
            hit = next((f for f in py_files if f == m[1].lstrip("/") or m[1].endswith("/" + f)), None)
            if hit:
                note(hit, 3, int(m[2]), "traceback")

        symbols: list[str] = []
        idents = self._identifiers(text)
        for rel in py_files:
            try:
                path = Path(repo_path, rel)
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                body = path.read_text(errors="replace")
            except OSError:
                continue
            weight = 0 if re.search(r"(^|/)(tests?|testing)(/|_)", rel) else 1  # tests rarely hold the fix
            for ident in idents:
                if ident not in body:
                    continue
                d = re.search(rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(ident)}\b", body, re.MULTILINE)
                if d:
                    line = body.count("\n", 0, d.start()) + 1
                    note(rel, 2 * weight + 1, line, f"defines {ident}")
                    symbols.append(f"{rel}:{line}: {ident}")
                else:
                    note(rel, weight, body.count("\n", 0, body.index(ident)) + 1, f"mentions {ident}")
        ranked = [f for f, _ in score.most_common(5) if score[f] > 0]
        return {
            "repo_map": self._repo_map(files, ranked),
            "candidates": [f"{f}:{why[f][0]} ({why[f][1]})" for f in ranked],
            "locations": [(f, why[f][0]) for f in ranked],
            "symbols": symbols[:10],
        }

    @staticmethod
    def _identifiers(text: str) -> list[str]:
        """Up to 8 code-like names from the issue: backticked code first, then snake_case/CamelCase/dotted names."""
        found: Counter[str] = Counter()
        for m in _BACKTICK.finditer(text):
            for tok in _IDENT.findall(m[1]):
                found[tok] += 3
        for tok in _IDENT.findall(text):
            if tok.lower() in _STOP:
                continue
            if "_" in tok or re.search(r"[a-z][A-Z]", tok) or tok[0].isupper() and len(tok) > 3:
                found[tok] += 1
        return [t for t, _ in found.most_common(8) if t.lower() not in _STOP]

    @staticmethod
    def _repo_map(files: list[str], focus: list[str]) -> str:
        if len(files) <= FULL_LISTING_UNDER:
            return ", ".join(files)
        per_dir: Counter[str] = Counter(str(Path(f).parent) for f in files if f.endswith(".py"))
        tree = "\n".join(f"{d}/ ({n} .py)" for d, n in sorted(per_dir.items()))
        focus_dirs = {str(Path(f).parent) for f in focus}
        listing = ", ".join(f for f in files if str(Path(f).parent) in focus_dirs)
        text = f"Directories:\n{tree}" + (f"\n\nFiles in the likely directories: {listing}" if listing else "")
        return text if len(text) <= MAP_LIMIT else text[:MAP_LIMIT] + "\n... (truncated)"

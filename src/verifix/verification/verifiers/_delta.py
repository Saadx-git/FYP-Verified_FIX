from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Callable

from verifix.models.patch import ChangeType
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.verification.base import VerificationContext

Finding = tuple[str, str, str, str]  # (rule, severity, message, "path:line")


def py_files(context: VerificationContext, *, existing_only: bool) -> list[str]:
    """Changed non-test python files; `existing_only` drops files the patch adds."""
    return [
        f.path for f in context.patch.changed_files
        if f.path.endswith(".py") and "/tests/" not in f"/{f.path}" and not f.path.rsplit("/", 1)[-1].startswith("test_")
        and f.change_type is not ChangeType.DELETED and not (existing_only and f.change_type is ChangeType.ADDED)
    ]


def _run(context: VerificationContext, argv: list[str], patched: bool) -> str:
    res = context.sandbox.execute(ExecutionRequest(
        command=[sys.executable, "-m", *argv], repo_path=context.repo_path,
        patch_diff=context.patch.diff if patched else "", limits=ResourceLimits(timeout_seconds=120),
    ))
    return res.stdout


def new_findings(
    context: VerificationContext, argv: Callable[[list[str]], list[str]],
    parse: Callable[[str], list[Finding]],
) -> list[Finding]:
    """Findings present with the patch applied but not on the unpatched baseline (line numbers ignored)."""
    after_files = py_files(context, existing_only=False)
    if not after_files:
        return []
    after = parse(_run(context, argv(after_files), patched=True))
    before_files = py_files(context, existing_only=True)
    before = parse(_run(context, argv(before_files), patched=False)) if before_files else []
    budget = Counter((r, m) for r, _, m, _ in before)
    fresh = []
    for f in after:
        if budget[(f[0], f[2])] > 0:
            budget[(f[0], f[2])] -= 1
        else:
            fresh.append(f)
    return fresh


def loads(text: str) -> object:
    try:
        return json.loads(text) if text.strip() else []
    except json.JSONDecodeError:
        return []

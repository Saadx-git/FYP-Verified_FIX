from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from verifix.sandbox.base import ExecutionRequest, ExecutionResult, ExecutionSandbox

_IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules")


class LocalSandbox(ExecutionSandbox):
    """Runs commands in a throwaway copy of the repo (no container isolation)."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="verifix-") as tmp:
            workdir = Path(tmp) / "repo"
            shutil.copytree(request.repo_path, workdir, ignore=_IGNORE)
            if request.patch_diff.strip():
                applied = subprocess.run(
                    ["git", "apply", "--whitespace=nowarn", "-"],
                    input=request.patch_diff, cwd=workdir, text=True, capture_output=True, check=False,
                )
                if applied.returncode != 0:
                    return ExecutionResult(
                        exit_code=applied.returncode,
                        stderr=f"patch failed to apply: {applied.stderr}",
                        duration_seconds=time.monotonic() - start,
                    )
            try:
                proc = subprocess.run(
                    request.command, cwd=workdir, text=True, capture_output=True, check=False,
                    timeout=request.limits.timeout_seconds or 120,
                    env={**_base_env(), **request.env},
                )
            except subprocess.TimeoutExpired as e:
                return ExecutionResult(
                    exit_code=124, stdout=_text(e.stdout), stderr=_text(e.stderr),
                    duration_seconds=time.monotonic() - start, timed_out=True,
                )
            return ExecutionResult(
                exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
                duration_seconds=time.monotonic() - start,
            )


def _base_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"PYTHONDONTWRITEBYTECODE": "1"}


def _text(v: str | bytes | None) -> str:
    return v.decode() if isinstance(v, bytes) else (v or "")

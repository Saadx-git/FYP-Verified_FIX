from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from verifix.sandbox.base import ExecutionRequest, ExecutionResult, ExecutionSandbox
from verifix.sandbox.local_sandbox import prepare_workspace

IMAGE = "verifix-sandbox:latest"
DOCKERFILE = """FROM docker.io/library/python:3.12-slim
RUN pip install --no-cache-dir pytest ruff bandit
WORKDIR /work
"""


class DockerSandbox(ExecutionSandbox):
    """Runs commands in a rootless container (podman or docker): no network, CPU/memory/PID limits, timeout.

    The patch is applied on the host, the workspace is bind-mounted, and the container is discarded after use.
    `install=True` first runs `pip install -e .` with the network enabled, for repos with their own dependencies.
    """

    def __init__(self, runtime: str | None = None, image: str = IMAGE, install: bool = False) -> None:
        self.runtime = runtime or next((r for r in ("podman", "docker") if shutil.which(r)), "")
        if not self.runtime:
            raise RuntimeError("no container runtime found (install podman or docker, or use --sandbox local)")
        self.image, self.install, self._ready = image, install, False

    def _ensure_image(self) -> None:
        if self._ready:
            return
        if subprocess.run([self.runtime, "image", "exists", self.image], capture_output=True, check=False).returncode != 0:
            with tempfile.TemporaryDirectory(prefix="verifix-image-") as ctx:
                (Path(ctx) / "Dockerfile").write_text(DOCKERFILE)
                built = subprocess.run([self.runtime, "build", "-q", "-t", self.image, ctx], capture_output=True, text=True, check=False)
            if built.returncode != 0:
                raise RuntimeError(f"could not build sandbox image: {built.stderr[-300:]}")
        self._ready = True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self._ensure_image()
        start = time.monotonic()
        lim = request.limits
        timeout = lim.timeout_seconds or 120
        with tempfile.TemporaryDirectory(prefix="verifix-ctr-") as tmp:
            workdir = Path(tmp) / "repo"
            if failed := prepare_workspace(request, workdir):
                return failed
            cmd = ["python" if c == sys.executable else c for c in request.command]
            network = self.install or lim.network_enabled
            if self.install:
                cmd = ["sh", "-c", "pip install -q -e . >/dev/null 2>&1; exec \"$@\"", "sh", *cmd]
            argv = [self.runtime, "run", "--rm", "--userns=keep-id", f"--memory={lim.memory_mb or 2048}m",
                    f"--cpus={lim.cpu_count or 2}", "--pids-limit=512", f"--network={'bridge' if network else 'none'}",
                    "-v", f"{workdir}:/work:Z", "-w", "/work", "-e", "PYTHONDONTWRITEBYTECODE=1",
                    *[x for k, v in request.env.items() for x in ("-e", f"{k}={v}")], self.image, *cmd]
            try:
                proc = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as e:
                return ExecutionResult(exit_code=124, stdout=_text(e.stdout), stderr=_text(e.stderr),
                                       duration_seconds=time.monotonic() - start, timed_out=True)
            return ExecutionResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
                                   duration_seconds=time.monotonic() - start)


def _text(v: str | bytes | None) -> str:
    return v.decode() if isinstance(v, bytes) else (v or "")

from __future__ import annotations

from verifix.sandbox.base import ExecutionRequest, ExecutionResult, ExecutionSandbox


class DockerSandbox(ExecutionSandbox):
    """Docker-backed sandbox."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """TODO: Implement Docker execution."""
        raise NotImplementedError

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ResourceLimits:
    timeout_seconds: int = 0
    memory_mb: int = 0
    cpu_count: int = 0
    network_enabled: bool = False


@dataclass
class ExecutionRequest:
    command: list[str] = field(default_factory=list)
    repo_path: str = ""
    patch_diff: str = ""
    env: dict[str, str] = field(default_factory=dict)
    limits: ResourceLimits = field(default_factory=ResourceLimits)


@dataclass
class ExecutionResult:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False


class ExecutionSandbox(ABC):
    """Isolated execution environment."""

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """TODO: Run a command in isolation."""
        raise NotImplementedError

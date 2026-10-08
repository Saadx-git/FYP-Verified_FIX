from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Which LLM(s) to use for each role."""

    # Groq model ids; override via config/CLI if Groq renames or retires one
    agent_model: str = "openai/gpt-oss-120b"
    reviewer_model: str = "openai/gpt-oss-20b"
    diagnosis_model: str = "openai/gpt-oss-20b"
    provider: str = "groq"


@dataclass
class ExecutionLimits:
    """Default sandbox limits."""

    timeout_seconds: int = 120
    memory_mb: int = 2048
    cpu_count: int = 2
    network_enabled: bool = False


@dataclass
class VerificationConfig:
    """Which verifiers are enabled and how."""

    enabled_verifiers: list[str] = field(default_factory=lambda: ["unit_tests"])
    fail_fast: bool = False


@dataclass
class RetryBudget:
    """Limits on repair attempts."""

    max_attempts: int = 3


@dataclass
class CostBudget:
    """Limits on spend."""

    max_tokens: int = 0
    max_api_cost_usd: float = 0.0
    max_wall_time_seconds: float = 0.0
    max_verification_cost: float = 0.0


@dataclass
class VerifixConfig:
    """Top-level configuration."""

    model: ModelConfig = field(default_factory=ModelConfig)
    limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    retry_budget: RetryBudget = field(default_factory=RetryBudget)
    cost_budget: CostBudget = field(default_factory=CostBudget)

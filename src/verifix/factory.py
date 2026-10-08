from __future__ import annotations

from dataclasses import dataclass, field

from verifix.agent.base import CodingAgent
from verifix.agent.orchestrator import AgentOrchestrator
from verifix.app import VerifixApplication
from verifix.config.models import VerifixConfig
from verifix.control.retry_budget import BudgetTracker
from verifix.control.stopping_policy import CostAwareStoppingPolicy
from verifix.diagnosis.diagnoser import FailureDiagnoser
from verifix.events.emitter import EventEmitter
from verifix.evidence.fusion import EvidenceFusionEngine
from verifix.evidence.store import EvidenceStore
from verifix.feedback.generator import FeedbackGenerator
from verifix.llm.client import GroqClient
from verifix.patching.generator import PatchGenerator
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.strategy.repair_selector import FixedRepairSelector, RepairStrategySelector
from verifix.strategy.verification_selector import VerificationStrategySelector
from verifix.verification.orchestrator import VerificationOrchestrator
from verifix.verification.registry import VerifierRegistry
from verifix.verification.verifiers.integration_test import IntegrationTestVerifier
from verifix.verification.verifiers.llm_review import LLMReviewVerifier
from verifix.verification.verifiers.requirement import RequirementVerifier
from verifix.verification.verifiers.security import SecurityVerifier
from verifix.verification.verifiers.static_analysis import StaticAnalysisVerifier
from verifix.verification.verifiers.unit_test import UnitTestVerifier

ALL_VERIFIERS = ["unit_tests", "static_analysis", "security", "integration_tests", "requirement", "llm_review"]


@dataclass
class HarnessOptions:
    """Switches that distinguish the full harness from baselines and ablations."""

    verifiers: list[str] = field(default_factory=lambda: list(ALL_VERIFIERS))
    max_attempts: int = 3
    feedback: str = "targeted"       # "targeted" | "raw"
    adaptive_verification: bool = True
    adaptive_stopping: bool = True
    adaptive_repair: bool = True
    fusion: str = "rules"            # "rules" | "tests_only"
    required: set[str] = field(default_factory=lambda: {"unit_tests"})


def build_application(agent: CodingAgent, options: HarnessOptions, emitter: EventEmitter | None = None,
                      client: GroqClient | None = None, config: VerifixConfig | None = None) -> VerifixApplication:
    config = config or VerifixConfig()
    config.retry_budget.max_attempts = options.max_attempts
    client = client or GroqClient()
    emitter = emitter or EventEmitter()

    registry = VerifierRegistry()
    candidates = [UnitTestVerifier(), StaticAnalysisVerifier(), SecurityVerifier(), IntegrationTestVerifier(),
                  RequirementVerifier(client, config.model.reviewer_model),
                  LLMReviewVerifier(client, config.model.reviewer_model)]
    for verifier in candidates:
        if verifier.name in options.verifiers:
            registry.register(verifier)
    enabled = [n for n in options.verifiers if n in registry.names()]
    config.verification.enabled_verifiers = enabled

    store = EvidenceStore()
    orchestrator = AgentOrchestrator(agent)
    tracker = BudgetTracker(config.retry_budget, config.cost_budget)
    return VerifixApplication(
        config=config,
        agent_orchestrator=orchestrator,
        patch_generator=PatchGenerator(orchestrator),
        sandbox=LocalSandbox(),
        verification_orchestrator=VerificationOrchestrator(registry, store, emitter, config.verification.fail_fast),
        evidence_store=store,
        fusion_engine=EvidenceFusionEngine(required=options.required & set(enabled),
                                        decide_on={"unit_tests"} if options.fusion == "tests_only" else None),
        diagnoser=FailureDiagnoser(),
        feedback_generator=FeedbackGenerator(mode=options.feedback),
        repair_selector=RepairStrategySelector() if options.adaptive_repair else FixedRepairSelector(),
        verification_selector=VerificationStrategySelector(enabled, adaptive=options.adaptive_verification),
        stopping_policy=CostAwareStoppingPolicy(
            min_expected_improvement=0.05 if options.adaptive_stopping else 0.0, budget_exhausted=tracker.exhausted),
        budget_tracker=tracker,
        emitter=emitter,
    )

from __future__ import annotations

from verifix.agent.orchestrator import AgentOrchestrator
from verifix.config.models import VerifixConfig
from verifix.control.retry_budget import BudgetTracker
from verifix.control.stopping_policy import CostAwareStoppingPolicy
from verifix.diagnosis.diagnoser import FailureDiagnoser
from verifix.evidence.fusion import EvidenceFusionEngine
from verifix.evidence.store import EvidenceStore
from verifix.feedback.generator import FeedbackGenerator
from verifix.patching.generator import PatchGenerator
from verifix.reporting.report import VerificationReport
from verifix.sandbox.base import ExecutionSandbox
from verifix.strategy.repair_selector import RepairStrategySelector
from verifix.strategy.verification_selector import VerificationStrategySelector
from verifix.verification.orchestrator import VerificationOrchestrator


class VerifixApplication:
    """Wires pipeline components together (dependency injection)."""

    def __init__(
        self,
        config: VerifixConfig,
        agent_orchestrator: AgentOrchestrator,
        patch_generator: PatchGenerator,
        sandbox: ExecutionSandbox,
        verification_orchestrator: VerificationOrchestrator,
        evidence_store: EvidenceStore,
        fusion_engine: EvidenceFusionEngine,
        diagnoser: FailureDiagnoser,
        feedback_generator: FeedbackGenerator,
        repair_selector: RepairStrategySelector,
        verification_selector: VerificationStrategySelector,
        stopping_policy: CostAwareStoppingPolicy,
        budget_tracker: BudgetTracker,
    ) -> None:
        self.config = config
        self.agent_orchestrator = agent_orchestrator
        self.patch_generator = patch_generator
        self.sandbox = sandbox
        self.verification_orchestrator = verification_orchestrator
        self.evidence_store = evidence_store
        self.fusion_engine = fusion_engine
        self.diagnoser = diagnoser
        self.feedback_generator = feedback_generator
        self.repair_selector = repair_selector
        self.verification_selector = verification_selector
        self.stopping_policy = stopping_policy
        self.budget_tracker = budget_tracker

    def run(self, repo: str, issue_id: str) -> VerificationReport:
        """TODO: Run the full verify-and-repair pipeline."""
        raise NotImplementedError

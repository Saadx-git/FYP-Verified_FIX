from __future__ import annotations

from verifix.agent.base import AgentRequest
from verifix.agent.orchestrator import AgentOrchestrator
from verifix.config.models import VerifixConfig
from verifix.control.retry_budget import BudgetTracker
from verifix.control.stopping_policy import CostAwareStoppingPolicy, StoppingDecision
from verifix.diagnosis.diagnoser import FailureDiagnoser
from verifix.events.emitter import EventEmitter
from verifix.evidence.fusion import EvidenceFusionEngine
from verifix.evidence.store import EvidenceStore
from verifix.feedback.generator import FeedbackGenerator
from verifix.issue.loader import load_issue
from verifix.models.cost import CostRecord
from verifix.models.evidence import DecisionType, VerificationDecision, VerificationStatus
from verifix.patching.generator import PatchGenerator
from verifix.patching.ranking import PatchRanker
from verifix.reporting.report import VerificationReport
from verifix.sandbox.base import ExecutionSandbox
from verifix.strategy.repair_selector import RepairStrategySelector
from verifix.strategy.verification_selector import VerificationStrategySelector
from verifix.verification.base import VerificationContext
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
        emitter: EventEmitter | None = None,
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
        self.emitter = emitter or EventEmitter()

    def run(self, repo: str, issue_id: str) -> VerificationReport:
        """Run the verify-and-repair loop until VERIFIED, or the stopping policy gives up."""
        emit = self.emitter.emit
        issue = load_issue(repo, issue_id)
        emit("run_started", repo=repo, issue_id=issue.issue_id, max_attempts=self.config.retry_budget.max_attempts)
        emit("issue_loaded", issue_id=issue.issue_id, title=issue.title, target_file=issue.target_file)

        report = VerificationReport(issue_id=issue.issue_id)
        patches: list = []
        feedback = None
        strategy_hint: dict = {}
        previous_diff: str | None = None
        while True:
            attempt = self.budget_tracker.state().attempt_count + 1
            emit("attempt_started", attempt=attempt, max_attempts=self.config.retry_budget.max_attempts)
            request = AgentRequest(issue=issue, repo_path=repo, feedback=feedback, context=strategy_hint)
            patch = self.patch_generator.generate(request)
            emit("patch_generated", attempt=attempt, patch_id=patch.patch_id, diff=patch.diff,
                 files=[f.path for f in patch.changed_files], plan=patch.plan.summary)

            context = VerificationContext(issue=issue, patch=patch, repo_path=repo, sandbox=self.sandbox)
            plan = self.verification_selector.select(patch, self.budget_tracker.state())
            emit("verification_plan", attempt=attempt, verifiers=plan.verifier_names,
                 focus=plan.parameters.get("focus", []), reason=plan.parameters.get("reason", ""))
            results = self.verification_orchestrator.run(context, plan)
            assessment = self.fusion_engine.fuse(patch.patch_id, results)
            decision = self.fusion_engine.decide(assessment)
            self.budget_tracker.record(CostRecord(
                tokens=patch.metadata.tokens_used + int(sum(r.cost for r in results)),
                execution_time_seconds=patch.metadata.generation_time_seconds + sum(r.duration_seconds for r in results),
                verification_cost=sum(r.cost for r in results),
            ))
            report.assessments.append(assessment)
            patches.append(patch)
            entry = {"attempt": attempt, "patch_id": patch.patch_id, "diff": patch.diff, "plan": patch.plan.summary,
                     "decision": decision.decision.value, "score": assessment.reliability_score, "diagnosis": None}
            report.history.append(entry)
            report.final_patch, report.attempts = patch, attempt
            emit("decision", attempt=attempt, decision=decision.decision.value,
                 score=assessment.reliability_score, rationale=decision.rationale)
            if decision.decision is DecisionType.VERIFIED:
                break

            state = self.budget_tracker.state()
            state.confidence = assessment.reliability_score
            state.expected_improvement = (1.0 - assessment.reliability_score) * 0.6 ** (attempt - 1)
            stuck = previous_diff is not None and patch.diff == previous_diff  # agent repeating itself
            previous_diff = patch.diff
            if stuck or self.stopping_policy.decide(state) is StoppingDecision.STOP:
                why = "agent repeated an identical patch" if stuck else "attempt/cost budget or low expected gain"
                decision = VerificationDecision(DecisionType.REJECT, assessment, f"stopped after {attempt} attempt(s) ({why}): {decision.rationale}")
                emit("decision", attempt=attempt, decision="reject", score=assessment.reliability_score, rationale=decision.rationale)
                break

            diagnosis = self.diagnoser.diagnose(patch, assessment)
            feedback = self.feedback_generator.generate(diagnosis)
            repair = self.repair_selector.select(diagnosis, state)
            self.verification_selector.observe(diagnosis, [r.verifier_name for r in results if r.status is VerificationStatus.FAIL])
            strategy_hint = {"strategy": repair.strategy_type.value, "previous_diff": patch.diff, **repair.parameters}
            entry["diagnosis"] = {"category": diagnosis.category.value, "summary": feedback.summary,
                                 "strategy": repair.strategy_type.value}
            emit("diagnosis", attempt=attempt, category=diagnosis.category.value,
                 summary=feedback.summary, details=feedback.details, strategy=repair.strategy_type.value)

        if decision.decision is not DecisionType.VERIFIED and len(patches) > 1:
            best = PatchRanker().rank(patches, report.assessments)[0]  # report the most trustworthy attempt, not just the last
            report.final_patch = best
        report.decision = decision
        report.cost = self.budget_tracker.state().spent
        emit("run_finished", decision=decision.decision.value, attempts=report.attempts,
             score=decision.assessment.reliability_score, diff=report.final_patch.diff if report.final_patch else "")
        return report

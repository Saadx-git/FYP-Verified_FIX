from __future__ import annotations

import argparse
import sys

from verifix.agent.base import CodingAgent
from verifix.agent.fake import FakeAgent
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
from verifix.patching.generator import PatchGenerator
from verifix.reporting.generator import HumanReadableReportGenerator, JSONReportGenerator
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.strategy.repair_selector import RepairStrategySelector
from verifix.strategy.verification_selector import VerificationStrategySelector
from verifix.verification.orchestrator import VerificationOrchestrator
from verifix.verification.registry import VerifierRegistry
from verifix.verification.verifiers.unit_test import UnitTestVerifier


def build_parser() -> argparse.ArgumentParser:
    """Build the verifix argument parser."""
    parser = argparse.ArgumentParser(prog="verifix")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run verify-and-repair on an issue")
    run.add_argument("--repo", required=True)
    run.add_argument("--issue", required=True, help="issue id or path to an issue JSON file")
    run.add_argument("--agent", choices=["fake", "mini"], default="mini")
    run.add_argument("--fake-patches", help="directory of *.diff files for --agent fake")
    run.add_argument("--max-attempts", type=int, default=3)
    run.add_argument("--verifiers", help="comma-separated verifier names (default: all available)")
    run.add_argument("--events", choices=["jsonl", "none"], default="none", help="stream JSONL events on stdout")
    run.add_argument("--report", help="write the JSON report to this path")

    sub.add_parser("verify", help="TODO: verify an existing patch")
    sub.add_parser("evaluate", help="TODO: run a benchmark evaluation")
    sub.add_parser("report", help="TODO: render a saved report")
    return parser


def _build_agent(args: argparse.Namespace) -> CodingAgent:
    if args.agent == "fake":
        return FakeAgent.from_dir(args.fake_patches) if args.fake_patches else FakeAgent([])
    raise SystemExit("--agent mini is not wired up yet; use --agent fake")


def build_application(args: argparse.Namespace, emitter: EventEmitter) -> VerifixApplication:
    config = VerifixConfig()
    config.retry_budget.max_attempts = args.max_attempts
    registry = VerifierRegistry()
    registry.register(UnitTestVerifier())
    enabled = args.verifiers.split(",") if args.verifiers else registry.names()
    config.verification.enabled_verifiers = enabled

    store = EvidenceStore()
    sandbox = LocalSandbox()
    agent_orchestrator = AgentOrchestrator(_build_agent(args))
    tracker = BudgetTracker(config.retry_budget, config.cost_budget)
    return VerifixApplication(
        config=config,
        agent_orchestrator=agent_orchestrator,
        patch_generator=PatchGenerator(agent_orchestrator),
        sandbox=sandbox,
        verification_orchestrator=VerificationOrchestrator(
            registry, store, emitter, fail_fast=config.verification.fail_fast),
        evidence_store=store,
        fusion_engine=EvidenceFusionEngine(required=set(enabled) & {"unit_tests"} or {"unit_tests"}),
        diagnoser=FailureDiagnoser(),
        feedback_generator=FeedbackGenerator(),
        repair_selector=RepairStrategySelector(),
        verification_selector=VerificationStrategySelector(enabled),
        stopping_policy=CostAwareStoppingPolicy(budget_exhausted=tracker.exhausted),
        budget_tracker=tracker,
        emitter=emitter,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        emitter = EventEmitter(sys.stdout if args.events == "jsonl" else None)
        report = build_application(args, emitter).run(repo=args.repo, issue_id=args.issue)
        if args.report:
            with open(args.report, "w") as fh:
                fh.write(JSONReportGenerator().generate(report))
        print(HumanReadableReportGenerator().generate(report), file=sys.stderr)
        return 0 if report.decision and report.decision.decision.value == "verified" else 1
    print(f"verifix {args.command}: not implemented yet", file=sys.stderr)
    return 2

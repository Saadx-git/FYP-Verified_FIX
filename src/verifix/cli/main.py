from __future__ import annotations

import argparse
import sys

from verifix.agent.base import CodingAgent
from verifix.agent.fake import FakeAgent
from verifix.agent.groq_agent import GroqAgent
from verifix.app import VerifixApplication
from verifix.config.models import VerifixConfig
from verifix.events.emitter import EventEmitter
from verifix.factory import ALL_VERIFIERS, HarnessOptions
from verifix.factory import build_application as build
from verifix.llm.client import GroqClient
from verifix.reporting.generator import HumanReadableReportGenerator, JSONReportGenerator


def build_parser() -> argparse.ArgumentParser:
    """Build the verifix argument parser."""
    parser = argparse.ArgumentParser(prog="verifix")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run verify-and-repair on an issue")
    run.add_argument("--repo", required=True)
    run.add_argument("--issue", required=True, help="issue id or path to an issue JSON file")
    run.add_argument("--agent", choices=["fake", "groq"], default="groq")
    run.add_argument("--fake-patches", help="directory of *.diff files for --agent fake")
    run.add_argument("--model", help="override the Groq agent model id")
    run.add_argument("--max-attempts", type=int, default=3)
    run.add_argument("--verifiers", help="comma-separated verifier names (default: all available)")
    run.add_argument("--feedback", choices=["targeted", "raw"], default="targeted")
    run.add_argument("--stopping", choices=["adaptive", "fixed"], default="adaptive")
    run.add_argument("--events", choices=["jsonl", "none"], default="none", help="stream JSONL events on stdout")
    run.add_argument("--report", help="write the JSON report to this path")

    sub.add_parser("verify", help="TODO: verify an existing patch")
    sub.add_parser("evaluate", help="TODO: run a benchmark evaluation")
    sub.add_parser("report", help="TODO: render a saved report")
    return parser


def _build_agent(args: argparse.Namespace, config: VerifixConfig) -> CodingAgent:
    if args.agent == "fake":
        return FakeAgent.from_dir(args.fake_patches) if args.fake_patches else FakeAgent([])
    model = config.model.agent_model if args.model is None else args.model
    return GroqAgent(GroqClient(), model)


def build_application(args: argparse.Namespace, emitter: EventEmitter) -> VerifixApplication:
    config = VerifixConfig()
    options = HarnessOptions(
        verifiers=args.verifiers.split(",") if args.verifiers else list(ALL_VERIFIERS),
        max_attempts=args.max_attempts, feedback=args.feedback, adaptive_stopping=args.stopping == "adaptive",
    )
    return build(_build_agent(args, config), options, emitter, config=config)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        emitter = EventEmitter(sys.stdout if args.events == "jsonl" else None)
        try:
            report = build_application(args, emitter).run(repo=args.repo, issue_id=args.issue)
        except (RuntimeError, FileNotFoundError) as exc:
            print(f"verifix: {exc}", file=sys.stderr)
            return 2
        if args.report:
            with open(args.report, "w") as fh:
                fh.write(JSONReportGenerator().generate(report))
        print(HumanReadableReportGenerator().generate(report), file=sys.stderr)
        return 0 if report.decision and report.decision.decision.value == "verified" else 1
    print(f"verifix {args.command}: not implemented yet", file=sys.stderr)
    return 2

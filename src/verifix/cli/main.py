from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from verifix.agent.base import CodingAgent
from verifix.agent.fake import FakeAgent
from verifix.agent.groq_agent import GroqAgent
from verifix.app import VerifixApplication
from verifix.config.models import VerifixConfig
from verifix.events.emitter import EventEmitter
from verifix.factory import ALL_VERIFIERS, HarnessOptions
from verifix.factory import build_application as build
from verifix.issue.resolve import resolve_issue, understand_issue
from verifix.issue.understanding import IssueUnderstander
from verifix.llm.client import GroqClient
from verifix.reporting.generator import HumanReadableReportGenerator, JSONReportGenerator
from verifix.reporting.html import HTMLReportGenerator, report_from_json
from verifix.store.runs import RunStore


def build_parser() -> argparse.ArgumentParser:
    """Build the verifix argument parser."""
    parser = argparse.ArgumentParser(prog="verifix")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run verify-and-repair on an issue")
    run.add_argument("--repo", required=True)
    run.add_argument("--issue", help="saved issue id, issue JSON path, GitHub issue URL, or #N")
    run.add_argument("--description", help="plain-English bug description (alternative to --issue)")
    run.add_argument("--description-file", help="file containing the bug description")
    run.add_argument("--agent", choices=["fake", "groq"], default="groq")
    run.add_argument("--fake-patches", help="directory of *.diff files for --agent fake")
    run.add_argument("--model", help="override the Groq agent model id")
    run.add_argument("--max-attempts", type=int, default=3)
    run.add_argument("--verifiers", help="comma-separated verifier names (default: all available)")
    run.add_argument("--feedback", choices=["targeted", "raw"], default="targeted")
    run.add_argument("--stopping", choices=["adaptive", "fixed"], default="adaptive")
    run.add_argument("--sandbox", choices=["local", "container"], default="local", help="container = rootless podman/docker, no network")
    run.add_argument("--events", choices=["jsonl", "none"], default="none", help="stream JSONL events on stdout")
    run.add_argument("--report", help="write the JSON report to this path")

    ver = sub.add_parser("verify", help="Verify an existing patch (no agent): exit 0 only if VERIFIED")
    ver.add_argument("--repo", required=True)
    ver.add_argument("--patch", required=True, help="unified git diff file to verify")
    ver.add_argument("--issue", help="saved issue id, issue JSON path, GitHub issue URL, or #N")
    ver.add_argument("--description", help="plain-English description of what the patch should fix")
    ver.add_argument("--description-file")
    ver.add_argument("--verifiers")
    ver.add_argument("--feedback", default="targeted")
    ver.add_argument("--stopping", default="adaptive")
    ver.add_argument("--sandbox", choices=["local", "container"], default="local")
    ver.add_argument("--events", choices=["jsonl", "none"], default="none")
    ver.add_argument("--report")
    un = sub.add_parser("understand", help="Interpret an issue (text, GitHub link or saved id) and print it as JSONL; runs nothing")
    un.add_argument("--repo", required=True)
    un.add_argument("--issue", help="saved issue id, issue JSON path, GitHub issue URL, or #N")
    un.add_argument("--description", help="plain-English bug description")
    un.add_argument("--description-file")

    ev = sub.add_parser("evaluate", help="Run baselines / full system / ablations over a dataset")
    ev.add_argument("--dataset", required=True, help="JSON list of instances")
    ev.add_argument("--config", default="full", help="comma-separated config names, or 'all' (see evaluation/baseline.py)")
    ev.add_argument("--agent", choices=["fake", "groq"], default="groq")
    ev.add_argument("--max-attempts", type=int, default=3)
    ev.add_argument("--model", help="override the Groq agent model id")
    ev.add_argument("--out", help="write full results JSON here")
    rp = sub.add_parser("report", help="Render a saved JSON report as HTML or text")
    rp.add_argument("--input", help="report JSON written by `run --report`")
    rp.add_argument("--repo", help="repo whose run history to read (.verifix/runs.db)")
    rp.add_argument("--list", action="store_true", help="list recent runs for --repo")
    rp.add_argument("--run", type=int, help="render run N from --repo's history")
    rp.add_argument("--format", choices=["html", "text"], default="html")
    rp.add_argument("--out", help="output file (default: stdout)")
    return parser


def _build_agent(args: argparse.Namespace, config: VerifixConfig) -> CodingAgent:
    if args.agent == "patch":
        return FakeAgent([Path(args.patch).read_text()])
    if args.agent == "fake":
        return FakeAgent.from_dir(args.fake_patches) if args.fake_patches else FakeAgent([])
    model = config.model.agent_model if args.model is None else args.model
    return GroqAgent(GroqClient(), model)


def build_application(args: argparse.Namespace, emitter: EventEmitter) -> VerifixApplication:
    config = VerifixConfig()
    options = HarnessOptions(
        verifiers=args.verifiers.split(",") if args.verifiers else list(ALL_VERIFIERS),
        max_attempts=args.max_attempts, feedback=args.feedback, adaptive_stopping=args.stopping == "adaptive",
        sandbox=args.sandbox,
    )
    return build(_build_agent(args, config), options, emitter, config=config)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify":
        args.agent, args.max_attempts, args.model = "patch", 1, None
    if args.command in ("run", "verify"):
        emitter = EventEmitter(sys.stdout if args.events == "jsonl" else None)
        try:
            description = Path(args.description_file).read_text() if args.description_file else args.description
            config = VerifixConfig()
            understander = IssueUnderstander(GroqClient(), config.model.diagnosis_model)
            issue_id = resolve_issue(args.repo, ref=args.issue, description=description,
                                     understander=understander, emitter=emitter)
            report = build_application(args, emitter).run(repo=args.repo, issue_id=issue_id)
        except (RuntimeError, FileNotFoundError) as exc:
            print(f"verifix: {exc}", file=sys.stderr)
            return 2
        RunStore(str(Path(args.repo) / ".verifix" / "runs.db")).save(
            report.issue_id, report.decision.decision.value, report.attempts, report.cost.tokens,
            report.decision.assessment.reliability_score, JSONReportGenerator().generate(report))
        if args.report:
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            with open(args.report, "w") as fh:
                fh.write(JSONReportGenerator().generate(report))
            Path(args.report).with_suffix(".html").write_text(HTMLReportGenerator().generate(report))
        print(HumanReadableReportGenerator().generate(report), file=sys.stderr)
        return 0 if report.decision and report.decision.decision.value == "verified" else 1
    if args.command == "understand":
        try:
            description = Path(args.description_file).read_text() if args.description_file else args.description
            understand_issue(args.repo, ref=args.issue, description=description,
                             understander=IssueUnderstander(GroqClient(), VerifixConfig().model.diagnosis_model),
                             emitter=EventEmitter(sys.stdout))
        except (RuntimeError, FileNotFoundError) as exc:
            print(f"verifix: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "report":
        if args.list:
            for rid, created, issue, decision, attempts, tokens, score in RunStore(str(Path(args.repo) / ".verifix" / "runs.db")).list():
                print(f"#{rid:<4} {time.strftime('%Y-%m-%d %H:%M', time.localtime(created))}  issue {issue:<14} {decision:<22} attempts={attempts} tokens={tokens} score={score}")
            return 0
        raw = RunStore(str(Path(args.repo) / ".verifix" / "runs.db")).get(args.run) if args.run else Path(args.input).read_text()
        if raw is None:
            print(f"verifix: run #{args.run} not found", file=sys.stderr)
            return 2
        rep = report_from_json(raw)
        text = (HTMLReportGenerator() if args.format == "html" else HumanReadableReportGenerator()).generate(rep)
        Path(args.out).write_text(text) if args.out else print(text)
        return 0
    if args.command == "evaluate":
        return _evaluate(args)
    print(f"verifix {args.command}: not implemented yet", file=sys.stderr)
    return 2


def _evaluate(args: argparse.Namespace) -> int:
    import json
    from dataclasses import asdict
    from pathlib import Path

    from verifix.evaluation.baseline import configurations, make_experiment
    from verifix.evaluation.benchmark import BenchmarkRunner

    names = list(configurations()) if args.config == "all" else args.config.split(",")
    client = GroqClient()
    config = VerifixConfig()

    def agent_factory(inst: dict) -> CodingAgent:
        if args.agent == "fake":
            return FakeAgent.from_dir(str(Path(inst["base"]) / inst["fake_patches"]))
        return GroqAgent(client, args.model or config.model.agent_model)

    results = []
    for name in names:
        try:
            exp = make_experiment(name, agent_factory, args.max_attempts, client)
        except KeyError:
            print(f"unknown config {name!r}; choose from {', '.join(configurations())}", file=sys.stderr)
            return 2
        results.append(BenchmarkRunner().run(exp, args.dataset))
        print(f"finished {name}", file=sys.stderr)
    cols = {"issue_resolution_rate": "resolved", "patch_correctness": "correct", "false_acceptance_rate": "false_acc",
            "false_rejection_rate": "false_rej", "regression_rate": "regress", "repair_success_after_feedback": "fb_repair",
            "repair_efficiency": "attempts", "token_api_usage": "tokens"}
    print(f"{'config':<12}" + "".join(f"{label:>11}" for label in cols.values()))
    for r in results:
        print(f"{r.experiment_name:<12}" + "".join(f"{getattr(r.metrics, c):>11.2f}" for c in cols))
    if args.out:
        Path(args.out).write_text(json.dumps([asdict(r) for r in results], indent=2))
    return 0

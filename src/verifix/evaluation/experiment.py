from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from verifix.agent.base import CodingAgent
from verifix.config.models import VerifixConfig
from verifix.evaluation.metrics import Metrics
from verifix.evaluation.oracle import oracle_check
from verifix.evaluation.result import EvaluationResult
from verifix.events.emitter import EventEmitter
from verifix.factory import HarnessOptions, build_application
from verifix.llm.client import GroqClient
from verifix.models.evidence import DecisionType

AgentFactory = Callable[[dict], CodingAgent]


@dataclass
class Experiment:
    """One harness configuration evaluated over a set of instances."""

    name: str = ""
    config: VerifixConfig = field(default_factory=VerifixConfig)
    options: HarnessOptions = field(default_factory=HarnessOptions)
    agent_factory: AgentFactory | None = None
    client: GroqClient | None = None

    def run_instance(self, inst: dict) -> dict:
        emitter = EventEmitter()
        app = build_application(self.agent_factory(inst), self.options, emitter, self.client, VerifixConfig())
        start = time.monotonic()
        try:
            report = app.run(inst["repo"], inst["issue"])
        except RuntimeError as exc:  # e.g. API failure: count as a rejected instance, keep the study going
            return {"id": inst["id"], "error": str(exc), "accepted": False, "correct": False, "regression": False,
                    "attempts": 0, "tokens": 0, "verification_tokens": 0, "seconds": time.monotonic() - start,
                    "first_attempt_failed": False}
        diff = report.final_patch.diff if report.final_patch else ""
        correct, regression = oracle_check(inst, diff)
        first = next((e["data"]["decision"] for e in emitter.events if e["type"] == "decision" and e["data"]["attempt"] == 1), "")
        return {
            "id": inst["id"], "accepted": report.decision.decision is DecisionType.VERIFIED,
            "decision": report.decision.decision.value, "correct": correct, "regression": regression,
            "attempts": report.attempts, "tokens": report.cost.tokens, "verification_tokens": report.cost.verification_cost,
            "seconds": time.monotonic() - start, "first_attempt_failed": first != "verified",
        }

    def run(self, instances: list[dict]) -> EvaluationResult:
        rows = [self.run_instance(i) for i in instances]
        return EvaluationResult(self.name, aggregate(rows), {r["id"]: r for r in rows})


def aggregate(rows: list[dict]) -> Metrics:
    n = len(rows) or 1
    accepted = [r for r in rows if r["accepted"]]
    correct = [r for r in rows if r["correct"]]
    failed_first = [r for r in rows if r["first_attempt_failed"]]
    rej_wrong = [r for r in rows if not r["accepted"] and not r["correct"]]
    return Metrics(
        n_instances=len(rows),
        issue_resolution_rate=len(accepted) / n,
        patch_correctness=len(correct) / n,
        regression_rate=sum(r["regression"] for r in rows) / n,
        verification_accuracy=(len([r for r in accepted if r["correct"]]) + len(rej_wrong)) / n,
        false_acceptance_rate=len([r for r in accepted if not r["correct"]]) / len(accepted) if accepted else 0.0,
        false_rejection_rate=len([r for r in correct if not r["accepted"]]) / len(correct) if correct else 0.0,
        repair_success_after_feedback=(
            len([r for r in failed_first if r["accepted"] and r["correct"]]) / len(failed_first) if failed_first else 0.0),
        verification_cost=sum(r["verification_tokens"] for r in rows) / n,
        repair_efficiency=sum(r["attempts"] for r in rows) / n,
        execution_time_seconds=sum(r["seconds"] for r in rows) / n,
        token_api_usage=int(sum(r["tokens"] for r in rows) / n),
    )


def load_instances(dataset_path: str) -> list[dict]:
    import json

    path = Path(dataset_path)
    items = json.loads(path.read_text())
    return [{**i, "id": i.get("id") or f"{i['repo']}#{i['issue']}", "repo": str((path.parent / i["repo"]).resolve()),
             "base": str(path.parent)} for i in items]

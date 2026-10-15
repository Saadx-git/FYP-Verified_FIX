"""A model-written reproduction test that invents requirements must not veto a patch the other evidence supports."""
import io
import json
import os
import shutil
import signal
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from verifix import runlog
from verifix.agent.base import AgentRequest
from verifix.agent.fake import FakeAgent
from verifix.agent.groq_agent import GroqAgent
from verifix.cli.main import main
from verifix.events.emitter import EventEmitter
from verifix.evidence.fusion import EvidenceFusionEngine
from verifix.evidence.store import EvidenceStore
from verifix.factory import HarnessOptions, build_application
from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.models.evidence import DecisionType, VerificationResult, VerificationStatus
from verifix.models.patch import CandidatePatch
from verifix.models.strategy import VerificationStrategy
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.verification.base import VerificationContext, Verifier
from verifix.verification.orchestrator import VerificationOrchestrator
from verifix.verification.registry import VerifierRegistry
from verifix.verification.verifiers.reproduction import SYSTEM, ReproductionVerifier

FIXTURES = Path(__file__).parent / "fixtures"
P, W, F = VerificationStatus.PASS, VerificationStatus.WARNING, VerificationStatus.FAIL


def _fuse(**statuses):
    results = [VerificationResult(name, st, 1.0) for name, st in statuses.items()]
    engine = EvidenceFusionEngine(required={"unit_tests"})
    return engine.decide(engine.fuse("p", results))


def test_a_failing_generated_test_is_overruled_when_requirement_and_project_tests_pass():
    d = _fuse(unit_tests=W, reproduction=F, requirement=P)
    assert d.decision is DecisionType.VERIFIED and "may over-specify the issue" in d.rationale
    assert _fuse(unit_tests=P, reproduction=F, requirement=P).decision is DecisionType.VERIFIED


def test_the_generated_test_still_decides_when_nothing_corroborates_the_patch():
    assert _fuse(unit_tests=P, reproduction=F).decision is DecisionType.REPAIR_REQUIRED               # requirement did not run
    assert _fuse(unit_tests=P, reproduction=F, requirement=F).decision is DecisionType.REPAIR_REQUIRED  # requirement agrees it is wrong
    assert _fuse(unit_tests=F, reproduction=F, requirement=P).decision is DecisionType.REPAIR_REQUIRED  # the project's own tests fail
    assert _fuse(unit_tests=P, reproduction=F, requirement=P, security=F).decision is DecisionType.REPAIR_REQUIRED  # any other failure
    assert _fuse(unit_tests=P, reproduction=P, requirement=P).rationale == "all required evidence passed"


class _Stub(Verifier):
    def __init__(self, name, status, ran):
        self.name, self.status, self.ran = name, status, ran

    def verify(self, context):
        self.ran.append(self.name)
        return VerificationResult(self.name, self.status, 1.0)


def _orchestrate(first_failure):
    ran, emitter = [], EventEmitter()
    reg = VerifierRegistry()
    for name, st in (("unit_tests", F if first_failure == "unit_tests" else P), ("reproduction", F if first_failure == "reproduction" else P),
                     ("requirement", P), ("llm_review", P)):
        reg.register(_Stub(name, st, ran))
    ctx = VerificationContext(patch=CandidatePatch(patch_id="p"))
    VerificationOrchestrator(reg, EvidenceStore(), emitter).run(
        ctx, VerificationStrategy(["unit_tests", "reproduction", "requirement", "llm_review"], {"skip_expensive_on_fail": True}))
    return ran, [e["data"]["verifier"] for e in emitter.events if e["type"] == "verifier_skipped"]


def test_the_requirement_check_is_not_skipped_by_a_failed_reproduction_test_but_is_by_other_failures():
    assert _orchestrate("reproduction") == (["unit_tests", "reproduction", "requirement"], ["llm_review"])
    ran, skipped = _orchestrate("unit_tests")
    assert "requirement" not in ran and "requirement" in skipped


def test_the_generator_is_told_not_to_invent_requirements_and_sees_the_existing_tests(tmp_path):
    seen = []

    def transport(body):
        seen.append(body["messages"])
        return {"choices": [{"message": {"content": json.dumps({"test_code": "def test_x():\n    assert False\n"})}}], "usage": {}}
    repo = tmp_path / "r"
    shutil.copytree(FIXTURES / "discount", repo, ignore=shutil.ignore_patterns("runs", "runs.db", "logs"))
    issue = load_issue(str(repo), "142")
    issue.fail_to_pass = []
    ctx = VerificationContext(issue=issue, repo_path=str(repo), sandbox=LocalSandbox(), patch=CandidatePatch(patch_id="p", diff=""))
    ReproductionVerifier(GroqClient(api_key="k", cache_dir=None, transport=transport), "m").verify(ctx)
    assert "Assert ONLY behaviour the report explicitly states" in seen[0][0]["content"] == SYSTEM or "ONLY behaviour" in SYSTEM
    assert "never add edge cases the report does not mention" in SYSTEM and "negative" in SYSTEM
    assert "do not contradict them" in seen[0][1]["content"] and "test_never_negative" in seen[0][1]["content"]


def test_a_cancelled_run_is_logged_as_cancelled_and_the_signal_handler_is_restored(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    before = signal.getsignal(signal.SIGTERM)

    def killed(repo, issue_id):
        os.kill(os.getpid(), signal.SIGTERM)  # what the sidebar's Cancel does to the CLI
        raise AssertionError("SIGTERM should have interrupted the run")
    monkeypatch.setattr("verifix.cli.main.build_application", lambda a, e: SimpleNamespace(run=killed))
    demo = FIXTURES / "demo-retry"
    with pytest.raises(KeyboardInterrupt):
        main(["run", "--repo", str(demo), "--issue", "142", "--agent", "fake"])
    assert signal.getsignal(signal.SIGTERM) is before
    (log,) = list((tmp_path / "logs").glob("2*.jsonl"))
    end = json.loads(log.read_text().splitlines()[-1])
    assert end["type"] == "log_end" and end["data"]["status"] == "cancelled"
    assert runlog.load_runs(tmp_path / "logs")[0]["end"]["status"] == "cancelled"


def test_the_agent_reports_each_step_and_rate_limit_waits(tmp_path, monkeypatch):
    monkeypatch.setattr("verifix.llm.client.time.sleep", lambda s: None)
    answers = iter(["429", {"id": "1", "type": "function", "function": {"name": "search", "arguments": json.dumps({"pattern": "def "})}},
                    {"id": "2", "type": "function", "function": {"name": "submit", "arguments": json.dumps({"summary": "done"})}}])

    def transport(body):
        a = next(answers)
        if a == "429":
            raise urllib.error.HTTPError("u", 429, "slow down", {"retry-after": "7"}, io.BytesIO(b"limit"))
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [a]}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}}
    repo = tmp_path / "r"
    shutil.copytree(FIXTURES / "clamp", repo, ignore=shutil.ignore_patterns("runs", "runs.db", "logs"))
    agent = GroqAgent(GroqClient(api_key="k", cache_dir=None, transport=transport), "m")
    emitter = EventEmitter()
    build_application(agent, HarnessOptions(verifiers=["unit_tests"]), emitter)  # the factory hands the run's emitter to the agent
    assert agent.emitter is emitter
    agent.generate_patch(AgentRequest(issue=load_issue(str(repo), "7"), repo_path=str(repo)))
    kinds = [(e["type"], e["data"].get("seconds"), e["data"].get("tools")) for e in emitter.events]
    assert ("llm_wait", 7, None) in kinds
    assert [k for k in kinds if k[0] == "agent_step"] == [("agent_step", None, ["search"]), ("agent_step", None, ["submit"])]


def test_fake_agents_without_an_emitter_are_unaffected():
    agent = FakeAgent([])
    build_application(agent, HarnessOptions(verifiers=["unit_tests"]), EventEmitter())
    assert not hasattr(agent, "emitter")

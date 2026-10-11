import json
import shutil
from pathlib import Path

import pytest

from verifix.events.emitter import EventEmitter
from verifix.issue.resolve import understand_issue
from verifix.issue.understanding import IssueUnderstander
from verifix.llm.client import GroqClient

FIX = Path(__file__).parent / "fixtures" / "clamp"
ANSWER = {"related_names": ["clamp"], "title": "Clamp ignores bounds", "acceptance_criteria": ["both bounds clamped"],
          "requirements": [{"id": "R1", "description": "lower bound", "observed_behavior": "returns x", "expected_behavior": "returns lo"}]}


def _understander(answer, calls):
    def transport(body):
        calls.append(body)
        return {"choices": [{"message": {"content": json.dumps(answer)}}], "usage": {}}
    return IssueUnderstander(GroqClient(api_key="k", cache_dir=None, transport=transport), "m")


def _repo(tmp_path):
    repo = tmp_path / "r"
    shutil.copytree(FIX, repo)
    return str(repo)


def test_understand_reports_the_interpretation_and_runs_nothing(tmp_path):
    emitter, calls = EventEmitter(), []
    issue = understand_issue(_repo(tmp_path), ref=None, description="Camp is not restricted to range",
                             understander=_understander(ANSWER, calls), emitter=emitter)
    types = [e["type"] for e in emitter.events]
    assert types == ["understanding_issue", "issue_understood"] and len(calls) == 1  # no run_started, no agent, no verifiers
    data = emitter.events[-1]["data"]
    assert data["issue_id"] == issue.issue_id and data["title"] == "Clamp ignores bounds" and data["unclear"] == ""
    assert data["requirements"] == [{"id": "R1", "description": "lower bound", "observed": "returns x", "expected": "returns lo"}]
    assert data["acceptance_criteria"] == ["both bounds clamped"]


def test_understand_reports_the_question_for_an_unmatched_report(tmp_path):
    emitter = EventEmitter()
    understand_issue(_repo(tmp_path), ref=None, description="camps beyond player distance",
                     understander=_understander({"related_names": [], "clarification": "What is a camp?"}, []), emitter=emitter)
    assert emitter.events[-1]["data"]["unclear"] == "What is a camp?"


def test_understand_a_saved_issue_needs_no_llm_call(tmp_path):
    calls = []
    understand_issue(_repo(tmp_path), ref="7", description=None, understander=_understander(ANSWER, calls), emitter=EventEmitter())
    assert calls == []


def test_confirmed_run_reuses_the_interpreted_issue_without_a_second_interpretation(tmp_path):
    from verifix.agent.fake import FakeAgent
    from verifix.factory import HarnessOptions, build_application
    repo = _repo(tmp_path)
    calls = []
    issue = understand_issue(repo, ref=None, description="Camp is not restricted to range",
                             understander=_understander(ANSWER, calls), emitter=EventEmitter())
    diff = (FIX / "patches" / "2-complete.diff").read_text()
    report = build_application(FakeAgent([diff]), HarnessOptions(verifiers=["unit_tests"])).run(repo, issue.issue_id)
    assert report.decision.decision.value == "verified" and len(calls) == 1  # still only the one interpretation call


@pytest.mark.parametrize("flag", ["--issue", "--description"])
def test_cli_understand_requires_a_source(flag):
    from verifix.cli.main import build_parser
    assert build_parser().parse_args(["understand", "--repo", "x", flag, "y"]).command == "understand"

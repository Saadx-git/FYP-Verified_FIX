import json
import shutil
from pathlib import Path

from verifix.agent.fake import FakeAgent
from verifix.events.emitter import EventEmitter
from verifix.factory import HarnessOptions, build_application
from verifix.issue.understanding import IssueUnderstander
from verifix.llm.client import GroqClient

FIX = Path(__file__).parent / "fixtures" / "clamp"
GOOD = (FIX / "patches" / "2-complete.diff").read_text()


def _understander(answer, seen):
    def transport(body):
        seen.append(body["messages"])
        return {"choices": [{"message": {"content": json.dumps(answer)}}], "usage": {}}
    return IssueUnderstander(GroqClient(api_key="k", cache_dir=None, transport=transport), "m")


def test_understanding_is_grounded_in_the_repo_and_flags_reports_that_do_not_match(tmp_path):
    seen = []
    ok = _understander({"related_names": ["clamp"], "title": "clamp ignores bounds", "requirements": [], "acceptance_criteria": []}, seen)
    assert ok.understand("i1", "Camp is not restricted to range", str(FIX)).unclear == ""
    user = seen[0][1]["content"]
    assert "mathx/clamp.py: clamp" in user and "Camp is not restricted to range" in user  # outline lets it map Camp -> clamp
    assert "typo" in seen[0][0]["content"] and "never invent" in seen[0][0]["content"]
    # a report that cites no real repository name is unclear, even if the model sounds confident
    bad = _understander({"related_names": [], "clarification": "Which function do you mean?"}, [])
    assert bad.understand("i2", "camps beyond player distance", str(FIX)).unclear == "Which function do you mean?"
    invented = _understander({"related_names": ["CampPlacer"], "clarification": "What is a camp?"}, [])
    assert invented.understand("i3", "camps beyond player distance", str(FIX)).unclear == "What is a camp?"
    # the model flagging a typo while still naming the real function must NOT stop the run
    typo = _understander({"related_names": ["clamp"], "clarification": "Camp looks like a typo for clamp", "requirements": []}, [])
    assert typo.understand("i4", "Camp is not restricted to range", str(FIX)).unclear == ""


def _repo(tmp_path, unclear=""):
    repo = tmp_path / "r"
    shutil.copytree(FIX, repo)
    issue = json.loads((repo / ".verifix/issues/7.json").read_text())
    (repo / ".verifix/issues/7.json").write_text(json.dumps({**issue, "unclear": unclear}))
    return str(repo)


def test_unclear_issue_stops_before_any_agent_call(tmp_path):
    agent, emitter = FakeAgent([GOOD]), EventEmitter()
    report = build_application(agent, HarnessOptions(verifiers=["unit_tests"]), emitter).run(
        _repo(tmp_path, unclear="Which function should be restricted?"), "7")
    types = [e["type"] for e in emitter.events]
    assert agent.requests == [] and report.attempts == 0 and report.decision.decision.value == "insufficient_evidence"
    assert "issue_unclear" in types and "issue_loaded" not in types and types[-1] == "run_finished"
    assert "Which function" in emitter.events[0]["data"]["question"]


def test_empty_patch_fails_fast_without_running_tests_and_tells_the_agent(tmp_path):
    agent, emitter = FakeAgent(["", GOOD]), EventEmitter()
    report = build_application(agent, HarnessOptions(verifiers=["unit_tests"]), emitter).run(_repo(tmp_path), "7")
    finished = [e["data"] for e in emitter.events if e["type"] == "verifier_finished"]
    assert [(d["patch_id"], d["verifier"], d["status"]) for d in finished] == [
        ("patch-1", "patch", "fail"), ("patch-2", "unit_tests", "pass")]  # no unit test run on the empty patch
    assert "no changes" in finished[0]["summary"]
    assert "no edits at all" in agent.requests[1].feedback.summary
    assert report.decision.decision.value == "verified" and report.attempts == 2

import json
import shutil
from pathlib import Path

from verifix.agent.base import AgentRequest
from verifix.agent.groq_agent import GroqAgent
from verifix.cli.main import main
from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.models.cost import BudgetState
from verifix.models.failure import FailureCategory, FailureDiagnosis, TargetedFeedback
from verifix.models.patch import CandidatePatch
from verifix.strategy.verification_selector import VerificationStrategySelector

FIXTURES = Path(__file__).parent / "fixtures"
FIX = FIXTURES / "clamp"
ALL = ["unit_tests", "static_analysis", "security", "reproduction", "requirement", "llm_review"]
FIRST_TRY = (FIX / "patches" / "1-incomplete.diff").read_text()


def _call(i, name, **a):
    return {"id": i, "type": "function", "function": {"name": name, "arguments": json.dumps(a)}}


def _agent(tmp_path, steps):
    seen = []
    it = iter(steps)

    def transport(body):
        seen.append(body["messages"])
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": next(it)}}], "usage": {}}
    repo = tmp_path / "repo"
    shutil.copytree(FIX, repo)
    return GroqAgent(GroqClient(api_key="k", cache_dir=None, transport=transport), "m"), repo, seen


def _request(repo, strategy):
    return AgentRequest(issue=load_issue(str(repo), "7"), repo_path=str(repo),
                        feedback=TargetedFeedback("lower bound missing", ["R2 not met"], ["mathx/clamp.py"]),
                        context={"strategy": strategy, "previous_diff": FIRST_TRY})


def test_revise_builds_on_the_previous_patch(tmp_path):
    agent, repo, seen = _agent(tmp_path, [
        [_call("1", "read_file", path="mathx/clamp.py")],
        [_call("2", "edit_file", path="mathx/clamp.py", old="return min(x, hi)", new="return max(lo, min(x, hi))")],
        [_call("3", "submit", summary="add lower bound")]])
    resp = agent.generate_patch(_request(repo, "revise_patch"))
    assert "ALREADY APPLIED" in seen[0][1]["content"] and "return min(x, hi)" in seen[0][1]["content"]  # shows current code
    assert "return max(lo, min(x, hi))" in resp.patch.diff and "-    return x" in resp.patch.diff  # diff is vs the ORIGINAL
    assert "return x" in (repo / "mathx/clamp.py").read_text()  # real repo untouched


def test_regenerate_starts_clean_and_does_not_show_the_failed_diff(tmp_path):
    agent, repo, seen = _agent(tmp_path, [[_call("1", "submit", summary="x")]])
    agent.generate_patch(_request(repo, "regenerate_patch"))
    prompt = seen[0][1]["content"]
    assert "Discard your earlier approach" in prompt and "ALREADY APPLIED" not in prompt
    assert "min(x, hi)" not in prompt and "return x" in prompt  # original code, previous diff withheld


def test_reexplore_shows_failed_diff_and_dependents(tmp_path):
    agent, repo, seen = _agent(tmp_path, [[_call("1", "submit", summary="x")]])
    (repo / "app.py").write_text("from mathx.clamp import clamp\n")
    agent.generate_patch(_request(repo, "reexplore_repository"))
    prompt = seen[0][1]["content"]
    assert "Re-explore" in prompt and "Previous diff" in prompt and "Files that import mathx/clamp.py: app.py" in prompt


def test_address_security_builds_on_previous_with_security_instruction(tmp_path):
    agent, repo, seen = _agent(tmp_path, [[_call("1", "submit", summary="x")]])
    agent.generate_patch(_request(repo, "address_security"))
    assert "ALREADY APPLIED" in seen[0][1]["content"] and "unsafe construct" in seen[0][1]["content"]


def test_unappliable_previous_patch_falls_back_to_showing_the_diff(tmp_path):
    agent, repo, seen = _agent(tmp_path, [[_call("1", "submit", summary="x")]])
    req = _request(repo, "revise_patch")
    req.context["previous_diff"] = "diff --git a/nope.py b/nope.py\n--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-a\n+b\n"
    agent.generate_patch(req)
    assert "ALREADY APPLIED" not in seen[0][1]["content"] and "Previous diff" in seen[0][1]["content"]


def _diag(cat):
    return FailureDiagnosis(cat)


def test_diagnosis_reorders_next_verification_and_environment_failures_run_only_unit_tests():
    sel = VerificationStrategySelector(ALL)
    state, patch = BudgetState(), CandidatePatch()
    assert sel.select(patch, state).verifier_names == ALL  # first attempt: default cheap-first order
    sel.observe(_diag(FailureCategory.REQUIREMENT_MISMATCH), ["requirement"])
    assert sel.select(patch, state).verifier_names[:2] == ["requirement", "reproduction"]
    sel.observe(_diag(FailureCategory.SECURITY_VIOLATION), ["security"])
    plan = sel.select(patch, state)
    assert plan.verifier_names[:2] == ["security", "static_analysis"] and plan.parameters["reason"] == "after security_violation"
    sel.observe(_diag(FailureCategory.TEST_ENVIRONMENT_FAILURE), ["unit_tests"])
    assert sel.select(patch, state).verifier_names == ["unit_tests"]
    off = VerificationStrategySelector(ALL, adaptive=False)  # ablation C: diagnosis does not steer verification
    off.observe(_diag(FailureCategory.SECURITY_VIOLATION), ["security"])
    assert off.select(patch, state).verifier_names == ALL


def test_pipeline_emits_verification_plan_steered_by_the_failure(tmp_path, capsys):
    demo = FIXTURES / "demo-retry"
    main(["run", "--repo", str(demo), "--issue", "142", "--agent", "fake", "--fake-patches", str(demo / "patches"),
          "--verifiers", "unit_tests,static_analysis,security", "--events", "jsonl", "--report", str(tmp_path / "r.json")])
    plans = [json.loads(line)["data"] for line in capsys.readouterr().out.splitlines() if '"verification_plan"' in line]
    assert plans[0]["verifiers"] == ["unit_tests", "static_analysis", "security"] and plans[0]["focus"] == []
    assert plans[1]["verifiers"][0] == "security" and plans[1]["reason"] == "after security_violation"

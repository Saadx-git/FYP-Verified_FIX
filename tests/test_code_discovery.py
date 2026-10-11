import json
import shutil
from pathlib import Path

from verifix.agent.base import AgentRequest
from verifix.agent.groq_agent import GroqAgent
from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.models.issue import Issue
from verifix.models.patch import CandidatePatch
from verifix.patching.diff import parse_changed_files
from verifix.repository.context_retriever import MAP_LIMIT, ContextRetriever
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.verification.base import VerificationContext
from verifix.verification.verifiers.reproduction import ReproductionVerifier

FIX = Path(__file__).parent / "fixtures" / "clamp"


def _repo(tmp_path, files):
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body)
    return str(tmp_path)


def test_traceback_path_ranks_that_file_first(tmp_path):
    repo = _repo(tmp_path, {"pkg/a.py": "def other(): ...\n", "pkg/core/calc.py": "def run():\n    return 1\n", "pkg/b.py": "x = 1\n"})
    body = 'Crash:\n  File "/site/pkg/core/calc.py", line 2, in run\nValueError'
    got = ContextRetriever().retrieve(repo, Issue(title="boom", body=body))
    assert got["candidates"][0].startswith("pkg/core/calc.py:2 (traceback")


def test_identifiers_become_candidates_and_symbols_without_any_target(tmp_path):
    repo = _repo(tmp_path, {"lib/pricing.py": "class DiscountCalculator:\n    def apply_discount(self): ...\n",
                            "lib/other.py": "y = 2\n", "tests/test_x.py": "apply_discount\n"})
    got = ContextRetriever().retrieve(repo, Issue(title="`apply_discount` is wrong", body="DiscountCalculator misbehaves"))
    assert got["candidates"][0].startswith("lib/pricing.py") and any("apply_discount" in s for s in got["symbols"])
    assert "lib/other.py" not in " ".join(got["candidates"])


def test_big_repo_map_is_truncated_and_never_dumps_every_file(tmp_path):
    repo = _repo(tmp_path, {f"pkg{i % 50}/mod_{i}.py": "x = 1\n" for i in range(500)})
    got = ContextRetriever().retrieve(repo, Issue(title="nothing matches here", body=""))
    assert len(got["repo_map"]) <= MAP_LIMIT + 30 and "Directories:" in got["repo_map"] and got["candidates"] == []


def _call(i, name, **a):
    return {"id": i, "type": "function", "function": {"name": name, "arguments": json.dumps(a)}}


def _agent(tmp_path, steps):
    seen, it = [], iter(steps)

    def transport(body):
        seen.append(body["messages"])
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": next(it)}}], "usage": {}}
    repo = tmp_path / "repo"
    shutil.copytree(FIX, repo)
    return GroqAgent(GroqClient(api_key="k", cache_dir=None, transport=transport), "m"), repo, seen


def test_agent_finds_code_itself_and_edits_several_files(tmp_path):
    agent, repo, seen = _agent(tmp_path, [
        [_call("1", "list_dir", path=".")],
        [_call("2", "search", pattern="def clamp", path="mathx")],
        [_call("3", "edit_file", path="mathx/clamp.py", old="    return x", new="    return max(lo, min(x, hi))")],
        [_call("4", "edit_file", path="mathx/__init__.py", old="", new="")],  # old='' matches many times -> error, no change
        [_call("5", "submit", summary="clamp both ends")]])
    (repo / "mathx/helpers.py").write_text("VALUE = 1\n")
    resp = agent.generate_patch(AgentRequest(issue=load_issue(str(repo), "7"), repo_path=str(repo)))
    tool_results = [m["content"] for msgs in seen[-1:] for m in msgs if m.get("role") == "tool"]
    assert "mathx/" in tool_results[0] and "mathx/clamp.py:1" in tool_results[1] and tool_results[3].startswith("error")
    assert resp.plan.target_files == ["mathx/clamp.py"] and "target file" not in seen[0][1]["content"].lower()
    assert "Repository map" in seen[0][1]["content"] and "locate the relevant code yourself" in seen[0][0]["content"]


def test_bad_regex_and_path_escape_return_errors_instead_of_crashing(tmp_path):
    agent, repo, _ = _agent(tmp_path, [])
    assert agent._tool(repo, "search", {"pattern": "(unclosed"}).startswith("error")
    assert "outside" in agent._tool(repo, "list_dir", {"path": ".."})


def test_reproduction_prompt_uses_retrieved_code_from_the_original_repo(tmp_path):
    prompts = []

    def transport(body):
        prompts.append(body["messages"][1]["content"])
        return {"choices": [{"message": {"content": json.dumps({"test_code": "def test_x():\n    assert False\n"})}}], "usage": {}}
    repo = tmp_path / "r"
    shutil.copytree(FIX, repo)
    issue = load_issue(str(repo), "7")
    issue.fail_to_pass = []
    issue.title = "`clamp` does not restrict values"
    diff = (FIX / "patches" / "2-complete.diff").read_text()
    ctx = VerificationContext(issue=issue, repo_path=str(repo), sandbox=LocalSandbox(),
                              patch=CandidatePatch(patch_id="p", diff=diff, changed_files=parse_changed_files(diff)))
    ReproductionVerifier(GroqClient(api_key="k", cache_dir=None, transport=transport), "m").verify(ctx)
    assert "Current code around mathx/clamp.py" in prompts[0] and "return x" in prompts[0]
    assert "max(lo, min(x, hi))" not in prompts[0]  # stays independent of the patch

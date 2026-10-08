import json
import shutil
from pathlib import Path

from verifix.agent.base import AgentRequest
from verifix.agent.groq_agent import GroqAgent
from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.sandbox.base import ExecutionRequest
from verifix.sandbox.local_sandbox import LocalSandbox

FIXTURE = Path(__file__).parent / "fixtures" / "discount"


def _call(id_, name, **args):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _scripted(steps):
    it = iter(steps)

    def transport(body):
        calls = next(it)
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": calls}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    return transport


def test_agent_edits_scratch_copy_and_returns_applicable_diff(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    steps = [
        [_call("1", "read_file", path="pricing/discount.py")],
        [_call("2", "edit_file", path="pricing/discount.py", old="    return discount", new="    return max(0, amount - discount)")],
        [_call("3", "submit", summary="subtract discount, clamp at zero", confidence=0.9)],
    ]
    client = GroqClient(api_key="k", cache_dir=None, transport=_scripted(steps))
    issue = load_issue(str(repo), "142")
    resp = GroqAgent(client, "m").generate_patch(AgentRequest(issue=issue, repo_path=str(repo)))
    assert "max(0, amount - discount)" in resp.patch.diff
    assert resp.patch.metadata.tokens_used == 360 and resp.plan.summary.startswith("subtract")
    assert "return discount" in (repo / "pricing/discount.py").read_text()  # original repo untouched
    res = LocalSandbox().execute(ExecutionRequest(
        command=["python3", "-m", "pytest", "-q"], repo_path=str(repo), patch_diff=resp.patch.diff))
    assert res.exit_code == 0, res.stdout


def test_edit_outside_repo_is_rejected(tmp_path):
    agent = GroqAgent(GroqClient(api_key="k", cache_dir=None), "m")
    assert "outside" in agent._tool(tmp_path, "edit_file", {"path": "../x.py", "old": "a", "new": "b"})

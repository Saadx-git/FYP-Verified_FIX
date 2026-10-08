import json
import shutil
from pathlib import Path

import pytest

from verifix.issue.github import fetch_issue, looks_like_github_issue, parse_ref
from verifix.issue.loader import load_issue
from verifix.issue.resolve import resolve_issue
from verifix.issue.understanding import IssueUnderstander
from verifix.llm.client import GroqClient

FIXTURE = Path(__file__).parent / "fixtures" / "clamp"
ANSWER = {"title": "clamp ignores bounds", "requirements": [
    {"id": "R1", "description": "upper", "observed_behavior": "x", "expected_behavior": "hi"}],
    "acceptance_criteria": ["clamps both ends"], "target_file": "mathx/clamp.py"}


def _understander(answer=ANSWER):
    client = GroqClient(api_key="k", cache_dir=None, transport=lambda body: {
        "choices": [{"message": {"content": json.dumps(answer)}}], "usage": {}})
    return IssueUnderstander(client, "m")


def test_free_text_becomes_cached_structured_issue(tmp_path):
    repo = tmp_path / "r"
    shutil.copytree(FIXTURE, repo)
    iid = resolve_issue(str(repo), ref=None, description="clamp never limits values", understander=_understander())
    assert iid.startswith("adhoc-")
    issue = load_issue(str(repo), iid)
    assert issue.target_file == "mathx/clamp.py" and issue.requirements[0].expected_behavior == "hi"
    assert resolve_issue(str(repo), ref=iid, description=None, understander=_understander()) == iid  # reuse cached id


def test_hallucinated_target_file_is_dropped(tmp_path):
    repo = tmp_path / "r"
    shutil.copytree(FIXTURE, repo)
    iid = resolve_issue(str(repo), ref=None, description="bug", understander=_understander({**ANSWER, "target_file": "nope.py"}))
    assert load_issue(str(repo), iid).target_file == ""


def test_github_url_and_number_parsing_and_fetch():
    assert looks_like_github_issue("https://github.com/o/r/issues/12") and looks_like_github_issue("#7")
    assert not looks_like_github_issue("142-discount") and not looks_like_github_issue("issue.json")
    assert parse_ref("https://github.com/o/r/issues/12", ".") == ("o", "r", 12)
    calls = []

    def transport(url):
        calls.append(url)
        return {"title": "T", "body": "B", "comments": 1} if "comments" not in url else [{"body": "me too"}]
    number, title, body = fetch_issue("https://github.com/o/r/issues/12", ".", transport)
    assert (number, title) == (12, "T") and "me too" in body and len(calls) == 2


def test_pull_request_is_refused():
    with pytest.raises(RuntimeError, match="pull request"):
        fetch_issue("https://github.com/o/r/issues/3", ".", lambda url: {"pull_request": {}, "title": "x"})

import difflib
import json
import shutil
from pathlib import Path

import pytest

from verifix.agent.base import AgentRequest, AgentResponse
from verifix.agent.fake import FakeAgent
from verifix.agent.groq_agent import GroqAgent
from verifix.events.emitter import EventEmitter
from verifix.factory import HarnessOptions, build_application
from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.models.evidence import VerificationStatus
from verifix.models.patch import CandidatePatch
from verifix.patching.diff import is_test_path, parse_changed_files
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.verification.base import VerificationContext
from verifix.verification.verifiers.unit_test import UnitTestVerifier

FIX = Path(__file__).parent / "fixtures" / "clamp"
GOOD = (FIX / "patches" / "2-complete.diff").read_text()
LEGACY = "def test_legacy_already_broken():\n    assert 'old' == 'new'\n\n\ndef test_legacy_ok():\n    assert True\n"


def _repo(tmp_path, legacy=True):
    repo = tmp_path / "repo"
    shutil.copytree(FIX, repo)
    if legacy:
        (repo / "tests" / "test_legacy.py").write_text(LEGACY)  # fails before ANY patch, unrelated to the issue
    return repo


def _ctx(repo, diff):
    issue = load_issue(str(repo), "7")
    issue.fail_to_pass, issue.pass_to_pass = [], []  # as for a typed / GitHub issue
    return VerificationContext(issue=issue, repo_path=str(repo), sandbox=LocalSandbox(),
                               patch=CandidatePatch(patch_id="p", diff=diff, changed_files=parse_changed_files(diff)))


def test_preexisting_failures_are_reported_but_not_blamed_on_the_patch(tmp_path):
    res = UnitTestVerifier().verify(_ctx(_repo(tmp_path), GOOD))
    assert res.status is VerificationStatus.WARNING, [f.message for f in res.findings]
    assert "1 pre-existing failure" in res.findings[0].message
    assert any("pre-existing failure" in f.message and "test_legacy_already_broken" in f.message for f in res.findings)
    roles = {t.test_id.split("::")[-1]: t.role for t in res.tests}
    assert roles["test_legacy_already_broken"] == "preexisting" and roles["test_legacy_ok"] == "other"


def test_a_real_regression_is_still_blocking(tmp_path):
    repo = _repo(tmp_path)
    breaking = ("diff --git a/mathx/clamp.py b/mathx/clamp.py\n--- a/mathx/clamp.py\n+++ b/mathx/clamp.py\n@@ -1,3 +1,3 @@\n"
                " def clamp(x, lo, hi):\n     \"\"\"Restrict x to the inclusive range [lo, hi].\"\"\"\n-    return x\n+    return lo\n")
    res = UnitTestVerifier().verify(_ctx(repo, breaking))  # in-range values now come back as lo: test_in_range_unchanged regresses
    assert res.status is VerificationStatus.FAIL
    assert any(f.message.startswith("regression: ") and "test_in_range_unchanged" in f.message for f in res.findings)
    assert any("pre-existing" in f.message for f in res.findings)  # the old failure is still reported separately


def test_the_baseline_is_run_once_per_issue_and_only_when_something_fails(tmp_path):
    runs = []

    class Counting(LocalSandbox):
        def execute(self, request):
            runs.append(bool(request.patch_diff))
            return super().execute(request)
    clean = _ctx(_repo(tmp_path / "a", legacy=False), GOOD)
    clean.sandbox = Counting()
    assert UnitTestVerifier().verify(clean).status is VerificationStatus.PASS
    assert runs == [True]  # no failures -> no baseline run
    runs.clear()
    verifier, dirty = UnitTestVerifier(), _ctx(_repo(tmp_path / "b"), GOOD)
    dirty.sandbox = Counting()
    verifier.verify(dirty)
    verifier.verify(dirty)
    assert runs == [True, False, True]  # patched, baseline (once), patched again


def test_a_patch_that_edits_existing_tests_is_flagged(tmp_path):
    repo = _repo(tmp_path, legacy=False)
    old = (repo / "tests" / "test_clamp.py").read_text()
    body = "".join(difflib.unified_diff(old.splitlines(keepends=True), old.replace("== 10", "== 15").splitlines(keepends=True),
                                       "a/tests/test_clamp.py", "b/tests/test_clamp.py"))
    res = UnitTestVerifier().verify(_ctx(repo, GOOD + "diff --git a/tests/test_clamp.py b/tests/test_clamp.py\n" + body))
    assert res.status is VerificationStatus.WARNING, [f.message for f in res.findings]
    assert any("modifies existing test files: tests/test_clamp.py" in f.message for f in res.findings)


def test_is_test_path():
    assert all(is_test_path(p) for p in ("tests/test_a.py", "pkg/tests/x.py", "test_a.py", "a_test.py", "conftest.py", "pkg/conftest.py"))
    assert not any(is_test_path(p) for p in ("mathx/clamp.py", "src/contest.py", "latest.py", "pkg/attests_not.py"))


def test_the_agent_cannot_edit_test_files(tmp_path):
    repo = _repo(tmp_path, legacy=False)
    agent = GroqAgent(GroqClient(api_key="k", cache_dir=None), "m")
    out = agent._tool(repo, "edit_file", {"path": "tests/test_clamp.py", "old": "== 10", "new": "== 15"})
    assert out.startswith("error: editing test files is not allowed")
    assert "== 10" in (repo / "tests" / "test_clamp.py").read_text()
    assert agent._tool(repo, "edit_file", {"path": "mathx/clamp.py", "old": "    return x", "new": "    return lo"}) == "ok"


class FlakyAgent(FakeAgent):
    """Raises an API error on the first call, like a rate-limited LLM."""

    def __init__(self, diffs, error):
        super().__init__(diffs)
        self.error, self.failed = error, False

    def generate_patch(self, request: AgentRequest) -> AgentResponse:
        if not self.failed:
            self.failed = True
            raise RuntimeError(self.error)
        return super().generate_patch(request)


def test_an_api_error_in_one_attempt_does_not_erase_the_run(tmp_path):
    emitter = EventEmitter()
    report = build_application(FlakyAgent([GOOD], "Groq API error 429: rate limited"), HarnessOptions(verifiers=["unit_tests"]), emitter).run(
        str(_repo(tmp_path, legacy=False)), "7")
    assert report.decision.decision.value == "verified" and report.attempts == 2
    assert [e["data"]["message"] for e in emitter.events if e["type"] == "agent_error"] == ["Groq API error 429: rate limited"]
    first = next(e["data"] for e in emitter.events if e["type"] == "verifier_finished")
    assert first["verifier"] == "patch" and first["status"] == "fail" and "agent error: Groq API error 429" in first["summary"]
    assert report.history[0]["diagnosis"] is not None  # the failed attempt is kept in the report


def test_a_bad_api_key_fails_fast_instead_of_retrying(tmp_path):
    with pytest.raises(RuntimeError, match="401"):
        build_application(FlakyAgent([GOOD], "Groq API error 401: Invalid API Key"), HarnessOptions(verifiers=["unit_tests"])).run(
            str(_repo(tmp_path, legacy=False)), "7")


def test_end_to_end_a_correct_patch_is_verified_despite_a_preexisting_failure(tmp_path):
    emitter = EventEmitter()
    report = build_application(FakeAgent([GOOD]), HarnessOptions(verifiers=["unit_tests"]), emitter).run(str(_repo(tmp_path)), "7")
    assert report.decision.decision.value == "verified" and report.attempts == 1
    finished = next(e["data"] for e in emitter.events if e["type"] == "verifier_finished")
    assert finished["status"] == "warning" and "pre-existing" in finished["summary"]
    assert json.dumps(finished["tests"]).count("preexisting") == 1

import json
import shutil
from pathlib import Path

from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.models.evidence import VerificationStatus
from verifix.models.patch import CandidatePatch
from verifix.patching.diff import parse_changed_files
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.verification.base import VerificationContext
from verifix.verification.verifiers.reproduction import ReproductionVerifier

FIX = Path(__file__).parent / "fixtures" / "clamp"
GOOD_TEST = ("from mathx.clamp import clamp\n\n\ndef test_low():\n    assert clamp(-5, 0, 10) == 0\n\n\n"
             "def test_high():\n    assert clamp(50, 0, 10) == 10\n")
PASSING_TEST = "from mathx.clamp import clamp\n\n\ndef test_noop():\n    assert clamp(5, 0, 10) == 5\n"
BROKEN_TEST = "import does_not_exist\n\n\ndef test_x():\n    pass\n"


def _setup(tmp_path, tests):
    repo = tmp_path / "r"
    shutil.copytree(FIX, repo)
    issue = load_issue(str(repo), "7")
    issue.fail_to_pass = []  # as with a typed / GitHub issue: no failing test known up front
    answers = iter(tests)
    calls = []

    def transport(body):
        calls.append(body)
        return {"choices": [{"message": {"content": json.dumps({"test_code": next(answers)})}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    verifier = ReproductionVerifier(GroqClient(api_key="k", cache_dir=None, transport=transport), "m")

    def ctx(diff_name):
        diff = (FIX / "patches" / diff_name).read_text()
        patch = CandidatePatch(patch_id=diff_name, diff=diff, changed_files=parse_changed_files(diff))
        return VerificationContext(issue=issue, patch=patch, repo_path=str(repo), sandbox=LocalSandbox())
    return verifier, ctx, calls


def test_complete_patch_passes_and_incomplete_patch_fails(tmp_path):
    verifier, ctx, calls = _setup(tmp_path, [GOOD_TEST])
    good = verifier.verify(ctx("2-complete.diff"))
    assert good.status is VerificationStatus.PASS and good.cost == 15
    bad = verifier.verify(ctx("1-incomplete.diff"))  # same cached test, no second LLM call
    assert bad.status is VerificationStatus.FAIL and "test_low" in bad.findings[0].message
    assert len(calls) == 1


def test_test_that_passes_on_buggy_code_is_rejected_as_uncertain(tmp_path):
    verifier, ctx, calls = _setup(tmp_path, [PASSING_TEST, PASSING_TEST])
    res = verifier.verify(ctx("2-complete.diff"))
    assert res.status is VerificationStatus.UNCERTAIN and len(calls) == 2  # retried once, then gave up


def test_invalid_test_gets_one_retry_with_feedback(tmp_path):
    verifier, ctx, calls = _setup(tmp_path, [BROKEN_TEST, GOOD_TEST])
    assert verifier.verify(ctx("2-complete.diff")).status is VerificationStatus.PASS
    assert "invalid" in calls[1]["messages"][1]["content"]


def test_skipped_when_issue_already_has_failing_tests(tmp_path):
    verifier, ctx, calls = _setup(tmp_path, [])
    c = ctx("2-complete.diff")
    c.issue.fail_to_pass = ["test_clamp_high"]
    assert verifier.verify(c).status is VerificationStatus.NOT_RUN and not calls

import json
from pathlib import Path

from verifix.issue.loader import load_issue
from verifix.llm.client import GroqClient
from verifix.models.evidence import VerificationResult, VerificationStatus
from verifix.models.patch import CandidatePatch, RepairPlan
from verifix.patching.diff import parse_changed_files
from verifix.verification.base import VerificationContext
from verifix.verification.verifiers.llm_review import LLMReviewVerifier
from verifix.verification.verifiers.requirement import RequirementVerifier

FIXTURE = Path(__file__).parent / "fixtures" / "discount"
DIFF = (FIXTURE / "patches" / "2-correct.diff").read_text()


def _client(payload):
    def transport(body):
        assert body["response_format"] == {"type": "json_object"}
        return {"choices": [{"message": {"content": json.dumps(payload) if isinstance(payload, dict) else payload}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 10}}
    return GroqClient(api_key="k", cache_dir=None, transport=transport)


def _ctx():
    patch = CandidatePatch(patch_id="p", diff=DIFF, plan=RepairPlan(summary="clamp"), changed_files=parse_changed_files(DIFF))
    ctx = VerificationContext(issue=load_issue(str(FIXTURE), "142"), patch=patch, repo_path=str(FIXTURE))
    ctx.extra["prior_results"] = [VerificationResult("unit_tests", VerificationStatus.PASS)]
    return ctx


def test_requirement_pass_fail_and_unclear():
    ok = {"requirements": [{"id": "R1", "status": "met", "reason": "x"}, {"id": "R2", "status": "met", "reason": "y"}]}
    bad = {"requirements": [{"id": "R1", "status": "met", "reason": "x"}, {"id": "R2", "status": "not_met", "reason": "no clamp"}]}
    unclear = {"requirements": [{"id": "R1", "status": "unclear", "reason": "?"}]}
    run = lambda payload: RequirementVerifier(_client(payload), "m").verify(_ctx())
    assert run(ok).status is VerificationStatus.PASS and run(ok).cost == 60
    assert run(bad).status is VerificationStatus.FAIL
    assert run(unclear).status is VerificationStatus.UNCERTAIN
    assert run("not json at all").status is VerificationStatus.UNCERTAIN  # garbage is "no evidence", never a pass


def test_review_is_advisory_and_never_fails():
    v = lambda payload: LLMReviewVerifier(_client(payload), "m").verify(_ctx())
    assert v({"verdict": "approve", "concerns": []}).status is VerificationStatus.PASS
    assert v({"verdict": "reject", "concerns": ["bad"]}).status is VerificationStatus.WARNING
    assert v({"verdict": "wat"}).status is VerificationStatus.UNCERTAIN

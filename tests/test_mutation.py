import shutil
from pathlib import Path

from verifix.issue.loader import load_issue
from verifix.models.evidence import VerificationStatus
from verifix.models.patch import CandidatePatch
from verifix.patching.diff import parse_changed_files
from verifix.sandbox.local_sandbox import LocalSandbox
from verifix.verification.base import VerificationContext
from verifix.verification.verifiers.mutation import MutationVerifier, changed_lines

FIX = Path(__file__).parent / "fixtures" / "discount"


def _ctx(repo, diff):
    return VerificationContext(issue=load_issue(str(repo), "142"), repo_path=str(repo), sandbox=LocalSandbox(),
                               patch=CandidatePatch(patch_id="p", diff=diff, changed_files=parse_changed_files(diff)))


def test_changed_lines_tracks_new_file_numbers():
    diff = (FIX / "patches" / "2-correct.diff").read_text()
    assert changed_lines(diff) == {"pricing/discount.py": {4}}


def test_strong_tests_kill_mutants_weak_tests_do_not(tmp_path):
    diff = (FIX / "patches" / "2-correct.diff").read_text()
    res = MutationVerifier().verify(_ctx(FIX, diff))
    assert res.status is VerificationStatus.PASS and res.confidence >= 0.6, [f.message for f in res.findings]
    weak = tmp_path / "weak"
    shutil.copytree(FIX, weak)
    (weak / "tests" / "test_discount.py").write_text("def test_nothing():\n    assert True\n")
    res = MutationVerifier().verify(_ctx(weak, diff))
    assert res.status is VerificationStatus.WARNING and any("surviving mutant" in f.message for f in res.findings)


def test_no_python_changes_means_not_run():
    diff = "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-a\n+b\n"
    assert MutationVerifier().verify(_ctx(FIX, diff)).status is VerificationStatus.NOT_RUN

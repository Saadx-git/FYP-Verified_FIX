import shutil
from pathlib import Path

from verifix.cli.main import main
from verifix.models.evidence import PatchAssessment, VerificationResult, VerificationStatus
from verifix.models.patch import CandidatePatch
from verifix.patching.ranking import PatchRanker
from verifix.repository.dependency_analyzer import DependencyAnalyzer
from verifix.store.runs import RunStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_dependency_graph_and_dependents(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/core.py").write_text("def f(): ...\n")
    (tmp_path / "pkg/api.py").write_text("from pkg.core import f\nimport os\n")
    (tmp_path / "main.py").write_text("import pkg.api\nfrom pkg import core\n")
    g = DependencyAnalyzer().analyze(str(tmp_path))
    assert g["pkg/api.py"] == ["pkg/core.py"] and set(g["main.py"]) == {"pkg/__init__.py", "pkg/api.py", "pkg/core.py"}
    assert DependencyAnalyzer().dependents(str(tmp_path), "pkg/core.py") == ["main.py", "pkg/api.py"]


def test_ranker_prefers_fewer_failures_then_score_then_size():
    def asm(pid, statuses, score):
        return PatchAssessment(pid, score, [VerificationResult("v", s) for s in statuses])
    big = CandidatePatch(patch_id="big", diff="+a\n+b\n+c\n")
    small = CandidatePatch(patch_id="small", diff="+a\n")
    bad = CandidatePatch(patch_id="bad", diff="+a\n")
    ranked = PatchRanker().rank([bad, big, small], [asm("bad", [VerificationStatus.FAIL], 0.9),
                                                    asm("big", [VerificationStatus.PASS], 0.8),
                                                    asm("small", [VerificationStatus.PASS], 0.8)])
    assert [p.patch_id for p in ranked] == ["small", "big", "bad"]


def test_run_store_roundtrip(tmp_path):
    store = RunStore(str(tmp_path / "x" / "runs.db"))
    rid = store.save("142", "verified", 2, 100, 0.9, "{}")
    assert store.get(rid) == "{}" and store.list()[0][2] == "142" and store.get(999) is None


def test_verify_existing_patch_exit_codes(tmp_path, capsys):
    repo = tmp_path / "r"
    shutil.copytree(FIXTURES / "discount", repo)
    common = ["verify", "--repo", str(repo), "--issue", "142", "--verifiers", "unit_tests,static_analysis,security"]
    assert main([*common, "--patch", str(FIXTURES / "discount/patches/2-correct.diff")]) == 0
    assert main([*common, "--patch", str(Path(__file__).parent / "data/unit_fail.diff")]) == 1
    capsys.readouterr()
    assert main(["report", "--repo", str(repo), "--list"]) == 0
    listing = capsys.readouterr().out
    assert "verified" in listing and "reject" in listing  # both runs landed in the history
    assert main(["report", "--repo", str(repo), "--run", "1", "--format", "text"]) == 0


def test_integration_verifier_runs_only_when_tests_exist(tmp_path):
    repo = tmp_path / "r"
    shutil.copytree(FIXTURES / "discount", repo)
    (repo / "tests/integration").mkdir()
    (repo / "tests/integration/test_flow.py").write_text(
        "from pricing.discount import apply_discount\n\n\ndef test_flow():\n    assert apply_discount(100, 0.5) == 50\n")
    patch = str(FIXTURES / "discount/patches/2-correct.diff")
    assert main(["verify", "--repo", str(repo), "--issue", "142", "--patch", patch,
                 "--verifiers", "unit_tests,integration_tests"]) == 0
    (repo / "tests/integration/test_flow.py").write_text("def test_flow():\n    assert False\n")
    assert main(["verify", "--repo", str(repo), "--issue", "142", "--patch", patch,
                 "--verifiers", "unit_tests,integration_tests"]) == 1

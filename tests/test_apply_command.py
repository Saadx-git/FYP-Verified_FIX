import shutil
import subprocess
from pathlib import Path

from verifix.cli.main import main

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN = shutil.ignore_patterns("runs.db", "runs", "logs", "__pycache__")  # no leftover run history from other tests
UNFIT = Path(__file__).parent / "data" / "unit_fail.diff"  # a patch the tests reject (breaks the never-negative requirement)


def _run(repo: Path, patches: Path, attempts: int = 3):
    return main(["run", "--repo", str(repo), "--issue", "142", "--agent", "fake", "--fake-patches", str(patches),
                 "--verifiers", "unit_tests,security", "--max-attempts", str(attempts), "--report", str(repo / "out" / "r.json")])


def _discount(tmp_path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "discount", repo, ignore=CLEAN)
    return repo


def _unverified_repo(tmp_path) -> Path:
    repo = _discount(tmp_path)
    only_bad = tmp_path / "bad"
    only_bad.mkdir()
    shutil.copy(UNFIT, only_bad / "1.diff")
    assert _run(repo, only_bad, attempts=1) == 1  # rejected
    return repo


def test_a_verified_patch_applies_without_force(tmp_path, capsys):
    repo = _discount(tmp_path)
    assert _run(repo, FIXTURES / "discount" / "patches") == 0
    capsys.readouterr()
    assert main(["apply", "--repo", str(repo)]) == 0  # latest run, from the run history
    out = capsys.readouterr().out
    assert "applied to pricing/discount.py" in out and "UNVERIFIED" not in out
    assert "max(0, amount - discount)" in (repo / "pricing" / "discount.py").read_text()
    assert main(["apply", "--repo", str(repo)]) == 2  # already applied: reported, not silently "successful"


def test_an_unverified_patch_needs_force_and_says_what_failed(tmp_path, capsys):
    repo = _unverified_repo(tmp_path)
    before = (repo / "pricing" / "discount.py").read_text()
    capsys.readouterr()
    assert main(["apply", "--repo", str(repo)]) == 1
    err = capsys.readouterr().err
    assert "NOT verified" in err and "unit_tests" in err and "--force" in err
    assert (repo / "pricing" / "discount.py").read_text() == before  # nothing was touched
    assert main(["apply", "--repo", str(repo), "--force"]) == 0
    assert "UNVERIFIED" in capsys.readouterr().out
    assert (repo / "pricing" / "discount.py").read_text() != before


def test_apply_from_a_report_file_inside_a_bigger_git_repo(tmp_path, capsys):
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
    repo = outer / "project"
    shutil.copytree(FIXTURES / "discount", repo, ignore=CLEAN)
    subprocess.run(["git", "add", "-A"], cwd=outer, check=True)
    assert _run(repo, FIXTURES / "discount" / "patches") == 0
    capsys.readouterr()
    assert main(["apply", "--repo", str(repo), "--input", str(repo / "out" / "r.json")]) == 0
    assert "max(0, amount - discount)" in (repo / "pricing" / "discount.py").read_text()  # git alone would have skipped this silently


def test_apply_errors_are_clear(tmp_path, capsys):
    repo = _discount(tmp_path)
    assert main(["apply", "--repo", str(repo)]) == 2 and "no run found" in capsys.readouterr().err

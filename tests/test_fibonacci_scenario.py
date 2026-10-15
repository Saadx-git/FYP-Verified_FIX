"""The scenario that broke real use: a recursion with a flipped operator, in a project that already has an unrelated broken test."""
import difflib
import shutil
from pathlib import Path

from verifix.agent.fake import FakeAgent
from verifix.cli.main import main
from verifix.events.emitter import EventEmitter
from verifix.factory import HarnessOptions, build_application

FIB = Path(__file__).parent / "fixtures" / "fibonacci"
CLEAN = shutil.ignore_patterns("runs.db", "runs", "logs", "__pycache__", ".pytest_cache")
LEGACY = 'def test_old_report_format():\n    assert "v1" == "v2"   # broken long before this issue\n'


def _fix_diff(repo: Path) -> str:
    old = (repo / "fib.py").read_text()
    new = old.replace("fib(n - 1) - fib(n - 2)", "fib(n - 1) + fib(n - 2)")
    return "diff --git a/fib.py b/fib.py\n" + "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/fib.py", "b/fib.py"))


def _repo(tmp_path, legacy=True) -> Path:
    repo = tmp_path / "proj"
    shutil.copytree(FIB, repo, ignore=CLEAN)
    if legacy:
        (repo / "tests" / "test_legacy.py").write_text(LEGACY)
    (repo / ".verifix" / "issues").mkdir(parents=True, exist_ok=True)  # the saved issue `understand` would have produced
    (repo / ".verifix" / "issues" / "fib-1.json").write_text('{"issue_id": "fib-1", "title": "fib is wrong", "body": "fib(3) should be 2"}')
    return repo


def test_the_buggy_project_fails_some_tests_and_passes_others(tmp_path):
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=_repo(tmp_path, legacy=False), capture_output=True, text=True, check=False).stdout
    assert "3 failed, 2 passed" in out  # fib(0), fib(1), fib(2) happen to work; fib(3) and up do not


def test_the_fix_is_verified_even_though_an_unrelated_test_was_already_broken(tmp_path):
    repo, emitter = _repo(tmp_path), EventEmitter()
    agent = FakeAgent([_fix_diff(repo)])
    report = build_application(agent, HarnessOptions(verifiers=["unit_tests", "static_analysis", "security"]), emitter).run(str(repo), "fib-1")
    assert report.decision.decision.value == "verified" and report.attempts == 1
    unit = next(e["data"] for e in emitter.events if e["type"] == "verifier_finished" and e["data"]["verifier"] == "unit_tests")
    assert unit["status"] == "warning" and "5 passed, 1 pre-existing failure(s) not caused by this patch" in unit["summary"]
    roles = {t["id"].split("::")[-1]: t["role"] for t in unit["tests"]}
    assert roles["test_old_report_format"] == "preexisting" and roles["test_fib_3"] == "other"


def test_verify_then_apply_fixes_the_project(tmp_path, capsys):
    repo = _repo(tmp_path)
    patches = tmp_path / "patches"
    patches.mkdir()
    (patches / "1.diff").write_text(_fix_diff(repo))
    assert main(["run", "--repo", str(repo), "--issue", "fib-1", "--agent", "fake", "--fake-patches", str(patches),
                 "--verifiers", "unit_tests,static_analysis,security", "--report", str(tmp_path / "r.json")]) == 0
    capsys.readouterr()
    assert main(["apply", "--repo", str(repo)]) == 0
    assert "fib(n - 1) + fib(n - 2)" in (repo / "fib.py").read_text()
    import subprocess
    import sys
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_fib.py"], cwd=repo, capture_output=True, text=True, check=False).stdout
    assert "5 passed" in tests  # the project's own fib tests now pass

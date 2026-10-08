import json
from pathlib import Path

from verifix.cli.main import main

FIXTURE = Path(__file__).parent / "fixtures" / "discount"


def _run(tmp_path, patches, capsys, extra=()):
    out = tmp_path / "report.json"
    code = main(["run", "--repo", str(FIXTURE), "--issue", "142", "--agent", "fake",
                 "--fake-patches", str(patches), "--verifiers", "unit_tests,static_analysis,security", "--events", "jsonl", "--report", str(out), *extra])
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    return code, events, json.loads(out.read_text())


def test_repairs_on_second_attempt(tmp_path, capsys):
    code, events, report = _run(tmp_path, FIXTURE / "patches", capsys)
    types = [e["type"] for e in events]
    assert code == 0
    assert types[0] == "run_started" and types[-1] == "run_finished"
    assert types.count("attempt_started") == 2 and "diagnosis" in types
    assert report["decision"]["decision"] == "verified" and report["attempts"] == 2


def test_rejects_when_budget_exhausted(tmp_path, capsys):
    wrong_only = tmp_path / "p"
    wrong_only.mkdir()
    (wrong_only / "1.diff").write_text((Path(__file__).parent / "data" / "unit_fail.diff").read_text())
    code, _events, report = _run(tmp_path, wrong_only, capsys, ["--max-attempts", "2"])
    assert code == 1
    assert report["decision"]["decision"] == "reject" and report["attempts"] == 2


def test_security_verifier_blocks_eval_patch(tmp_path, capsys):
    _, events, _ = _run(tmp_path, FIXTURE / "patches", capsys)
    first = [e["data"] for e in events if e["type"] == "verifier_finished" and e["data"]["patch_id"] == "patch-1"]
    status = {d["verifier"]: d["status"] for d in first}
    assert status["unit_tests"] == "pass" and status["security"] == "fail"


def test_demo_retry_fixture_shows_planned_failure_then_success(tmp_path, capsys):
    demo = FIXTURE.parent / "demo-retry"
    out = tmp_path / "r.json"
    code = main(["run", "--repo", str(demo), "--issue", "142", "--agent", "fake", "--fake-patches", str(demo / "patches"),
                 "--verifiers", "unit_tests,static_analysis,security", "--report", str(out)])
    capsys.readouterr()
    report = json.loads(out.read_text())
    assert code == 0 and report["attempts"] == 2 and report["history"][0]["decision"] == "repair_required"

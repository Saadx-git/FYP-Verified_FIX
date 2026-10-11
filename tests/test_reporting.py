import json
from pathlib import Path

from verifix.cli.main import main
from verifix.reporting.html import report_from_json

FIXTURE = Path(__file__).parent / "fixtures" / "discount"


def test_report_html_roundtrip_and_cli(tmp_path, capsys):
    out = tmp_path / "r.json"
    main(["run", "--repo", str(FIXTURE), "--issue", "142", "--agent", "fake", "--fake-patches", str(FIXTURE / "patches"),
          "--verifiers", "unit_tests,static_analysis,security", "--report", str(out)])
    capsys.readouterr()
    html = out.with_suffix(".html").read_text()
    assert "VERIFIED" in html and "Attempt 1" in html and "Attempt 2" in html and "security_violation" in html
    assert "B307" in html or "eval" in html  # the rejected attempt's diff is kept in the history
    rep = report_from_json(out.read_text())
    assert rep.attempts == 2 and len(rep.history) == 2 and rep.decision.decision.value == "verified"
    dest = tmp_path / "again.html"
    assert main(["report", "--input", str(out), "--out", str(dest)]) == 0 and "Verifix report" in dest.read_text()
    assert main(["report", "--input", str(out), "--format", "text"]) == 0
    assert "VERIFIED" in capsys.readouterr().out
    assert json.loads(out.read_text())["history"][0]["diagnosis"]["category"] == "security_violation"


def test_html_report_lists_every_test_per_attempt_and_old_reports_still_load(tmp_path, capsys):
    demo = FIXTURE.parent / "demo-retry"
    out = tmp_path / "r.json"
    main(["run", "--repo", str(demo), "--issue", "142", "--agent", "fake", "--fake-patches", str(demo / "patches"),
          "--verifiers", "unit_tests,security", "--report", str(out)])
    capsys.readouterr()
    page = out.with_suffix(".html").read_text()
    assert page.count("<details") >= 2 and "unit_tests tests: 3 passed" in page
    assert "test_never_negative" in page and "fail_to_pass" in page and "pass_to_pass" in page
    raw = json.loads(out.read_text())
    for a in raw["assessments"]:
        for r in a["results"]:
            r.pop("tests", None)  # a report saved before this feature existed
    assert report_from_json(json.dumps(raw)).attempts == 2

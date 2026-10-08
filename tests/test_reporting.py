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

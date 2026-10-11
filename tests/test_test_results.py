import json
from pathlib import Path

from verifix.cli.main import main
from verifix.verification.verifiers.unit_test import collect_tests, parse_tests, pytest_cmd

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUT = """\
=================================== FAILURES ===================================
______________________________ test_never_negative ______________________________

    def test_never_negative():
>       assert apply_discount(10, 1.5) == 0
E       assert -5.0 == 0

tests/test_discount.py:11: AssertionError
=========================== slowest durations ============================
0.02s call     tests/test_discount.py::test_never_negative
0.01s call     tests/test_discount.py::test_discount_applied
=========================== short test summary info ============================
PASSED tests/test_discount.py::test_discount_applied
PASSED tests/test_discount.py::test_zero_rate_unchanged
FAILED tests/test_discount.py::test_never_negative - assert -5.0 == 0
XFAIL tests/test_discount.py::test_known_bug - reason
ERROR tests/test_broken.py::test_x
"""


def test_parse_tests_outcomes_roles_durations_and_messages():
    tests = {t.test_id.split("::")[-1]: t for t in parse_tests(
        OUTPUT, fail_to_pass=["test_never_negative"], pass_to_pass=["test_zero_rate_unchanged"])}
    assert tests["test_discount_applied"].outcome == "passed" and tests["test_discount_applied"].duration == 0.01
    assert tests["test_never_negative"].role == "fail_to_pass" and "assert -5.0 == 0" in tests["test_never_negative"].message
    assert tests["test_zero_rate_unchanged"].role == "pass_to_pass" and tests["test_zero_rate_unchanged"].message == ""
    assert tests["test_known_bug"].outcome == "xfailed" and tests["test_x"].outcome == "error"


def test_collect_tests_caps_keep_failures_first():
    lines = [f"PASSED t.py::test_{i}" for i in range(350)] + ["FAILED t.py::test_bad - boom"]
    tests, omitted = collect_tests("\n".join(lines))
    assert tests[0].outcome == "failed" and len(tests) == 301 and omitted == 50


def test_pytest_cmd_only_touches_pytest_commands():
    assert pytest_cmd(["python", "-m", "pytest", "-q"])[-2:] == ["--durations=0", "--durations-min=0"]
    assert pytest_cmd(["python", "runtests.py"]) == ["python", "runtests.py"]


def test_pipeline_events_and_report_keep_passing_and_failing_tests(tmp_path, capsys):
    demo = FIXTURES / "demo-retry"
    out = tmp_path / "r.json"
    main(["run", "--repo", str(demo), "--issue", "142", "--agent", "fake", "--fake-patches", str(demo / "patches"),
          "--verifiers", "unit_tests", "--events", "jsonl", "--report", str(out)])
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    finished = [e["data"] for e in events if e["type"] == "verifier_finished"]
    ids = {t["id"].split("::")[-1]: t for t in finished[-1]["tests"]}
    assert set(ids) == {"test_discount_applied", "test_zero_rate_unchanged", "test_never_negative"}
    assert finished[-1]["counts"] == {"passed": 3}
    assert ids["test_never_negative"]["role"] == "fail_to_pass" and ids["test_zero_rate_unchanged"]["role"] == "pass_to_pass"
    saved = json.loads(out.read_text())["decision"]["assessment"]["results"][0]["tests"]
    assert len(saved) == 3 and all(t["outcome"] == "passed" for t in saved)

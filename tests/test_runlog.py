import io
import json
import shutil
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from verifix import runlog
from verifix.cli.main import main
from verifix.llm.client import GroqClient

FIXTURES = Path(__file__).parent / "fixtures"
DEMO = FIXTURES / "demo-retry"


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _only_log(logdir: Path) -> Path:
    files = [p for p in logdir.glob("*.jsonl") if p.name != runlog.HOST_LOG]
    assert len(files) == 1, files
    return files[0]


def _run_demo(extra=()):
    return main(["run", "--repo", str(DEMO), "--issue", "142", "--agent", "fake", "--fake-patches", str(DEMO / "patches"),
                 "--verifiers", "unit_tests,static_analysis,security", *extra])


def test_a_cli_run_leaves_a_complete_log(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("VERIFIX_CLIENT", "vscode")
    assert _run_demo() == 0
    recs = _records(_only_log(tmp_path / "logs"))
    kinds = [r["type"] for r in recs]
    assert kinds[0] == "log_start" and kinds[-1] == "log_end"
    start, end = recs[0]["data"], recs[-1]["data"]
    assert start["command"] == "run" and start["client"] == "vscode" and "--issue" in start["argv"] and start["python"]
    assert {"run_started", "patch_generated", "verifier_finished", "decision", "diagnosis", "run_finished"} <= set(kinds)
    assert any(r["type"] == "verifier_finished" and r["data"]["verifier"] == "security" and r["data"]["status"] == "fail" for r in recs)
    assert (end["status"], end["exit_code"], end["decision"], end["attempts"], end["issue_id"]) == ("completed", 0, "verified", 2, "142")
    assert end["signals"] == [] and end["seconds"] >= 0


def test_llm_calls_are_recorded_with_tokens_cache_latency_and_secrets_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    transport = lambda body: {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    client = GroqClient(api_key="k", cache_dir=str(tmp_path / "cache"), transport=transport)
    msgs = [{"role": "user", "content": "my key is gsk_abcdefghij1234567890XYZ and ghp_abcdefghij1234567890"}]
    with runlog.RunLog.start_for("run", str(tmp_path), []) as log:
        client.chat("m", msgs, purpose="understand")
        client.chat("m", msgs, purpose="understand")  # served from the cache
    calls = [r["data"] for r in _records(log.path) if r["type"] == "llm_call"]
    assert [(c["purpose"], c["prompt_tokens"], c["completion_tokens"], c["cached"]) for c in calls] == [("understand", 7, 3, False), ("understand", 0, 0, True)]
    assert calls[0]["seconds"] >= 0 and calls[0]["response_preview"] == "hi"
    text = log.path.read_text()
    assert "gsk_abcdefghij" not in text and "ghp_abcdefghij" not in text and "[REDACTED]" in text
    assert _records(log.path)[-1]["data"]["tokens"] == 10


def test_content_modes_and_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    client = GroqClient(api_key="k", cache_dir=None, transport=lambda b: {"choices": [{"message": {"content": "x" * 5000}}], "usage": {}})
    for mode, check in (("off", lambda d: "request_preview" not in d), ("preview", lambda d: len(d["response_preview"]) < 1700 and "more chars" in d["response_preview"]),
                        ("full", lambda d: len(d["response_preview"]) == 5000)):
        monkeypatch.setenv("VERIFIX_LOG_CONTENT", mode)
        with runlog.RunLog.start_for("run", str(tmp_path), []) as log:
            client.chat("m", [{"role": "user", "content": "q"}])
        assert check(next(r["data"] for r in _records(log.path) if r["type"] == "llm_call")), mode


def test_llm_errors_and_retries_are_logged_as_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("verifix.llm.client.time.sleep", lambda s: None)
    calls = iter([429, 200, 400])

    def transport(body):
        code = next(calls)
        if code == 200:
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}
        raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"nope"))
    client = GroqClient(api_key="k", cache_dir=None, transport=transport)
    with runlog.RunLog.start_for("run", str(tmp_path), []) as log:
        client.chat("m", [{"role": "user", "content": "a"}], purpose="agent")          # 429 then success
        with pytest.raises(RuntimeError):
            client.chat("m", [{"role": "user", "content": "b"}], purpose="agent")      # hard 400
    recs = [r["data"] for r in _records(log.path) if r["type"] == "llm_call"]
    assert recs[0]["retries"] == 1 and "error" not in recs[0] and "400" in recs[1]["error"]
    assert {"llm_error", "llm_retries"} <= set(_records(log.path)[-1]["data"]["signals"])


def test_a_crash_is_logged_with_traceback_and_still_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))

    def boom(repo, issue_id):
        raise ValueError("kaboom in the pipeline")
    monkeypatch.setattr("verifix.cli.main.build_application", lambda a, e: SimpleNamespace(run=boom))
    with pytest.raises(ValueError, match="kaboom"):
        _run_demo()
    recs = _records(_only_log(tmp_path / "logs"))
    crash = next(r["data"] for r in recs if r["type"] == "crash")
    assert crash["type"] == "ValueError" and "kaboom" in crash["message"] and "boom" in crash["traceback"] and "Traceback" in crash["traceback"]
    end = recs[-1]["data"]
    assert end["status"] == "crashed" and end["exit_code"] is None and "crashed" in end["signals"]


def test_handled_errors_are_logged_but_not_as_crashes(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    assert main(["run", "--repo", str(DEMO), "--issue", "nope", "--agent", "fake"]) == 2
    recs = _records(_only_log(tmp_path / "logs"))
    assert any(r["type"] == "error" and "nope" in r["data"]["message"] for r in recs)
    assert recs[-1]["data"]["status"] == "completed" and recs[-1]["data"]["exit_code"] == 2


def test_an_unwritable_log_location_never_stops_a_run(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "a_file"
    blocker.write_text("x")
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(blocker / "logs"))  # cannot create a folder under a file
    assert _run_demo() == 0
    assert "run logging disabled" in capsys.readouterr().err


def test_signals_flag_the_patterns_worth_investigating():
    fin = lambda patch, verifier, status, summary="": ("verifier_finished", {"patch_id": patch, "verifier": verifier, "status": status, "summary": summary})
    assert "empty_patch" in runlog.compute_signals([fin("p1", "patch", "fail", "the agent produced no changes")], "completed")
    assert "verifier_crashed" in runlog.compute_signals([fin("p1", "security", "uncertain", "verifier crashed: boom")], "completed")
    assert "disagreement" in runlog.compute_signals([fin("p1", "unit_tests", "pass"), fin("p1", "requirement", "fail")], "completed")
    assert "disagreement" in runlog.compute_signals([fin("p1", "unit_tests", "fail"), fin("p1", "reproduction", "pass")], "completed")
    assert "disagreement" not in runlog.compute_signals([fin("p1", "unit_tests", "pass"), fin("p1", "requirement", "pass")], "completed")
    assert "unclear_issue" in runlog.compute_signals([("issue_unclear", {"question": "?"})], "completed")
    assert "stuck" in runlog.compute_signals([("patch_generated", {"diff": "d"}), ("patch_generated", {"diff": "d"})], "completed")
    got = runlog.compute_signals([("run_started", {"max_attempts": 3}), ("run_finished", {"decision": "reject", "attempts": 3})], "completed")
    assert {"rejected", "attempts_exhausted"} <= set(got)
    assert runlog.compute_signals([], "crashed") == ["crashed"]


def test_old_logs_are_pruned_and_the_host_log_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(runlog, "KEEP", 3)
    d = tmp_path / "logs"
    d.mkdir()
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(d))
    (d / runlog.HOST_LOG).write_text("{}\n")
    for i in range(6):
        (d / f"2026010{i}-000000-aaaaaa.jsonl").write_text("{}\n")
    with runlog.RunLog.start_for("run", str(tmp_path), []) as log:
        pass
    left = sorted(p.name for p in d.glob("*.jsonl"))
    assert runlog.HOST_LOG in left and log.path.name in left and len(left) == 4  # host log + 3 newest runs (incl. this one)
    assert "20260100-000000-aaaaaa.jsonl" not in left and "20260105-000000-aaaaaa.jsonl" in left


def test_logs_command_lists_shows_and_summarizes(tmp_path, monkeypatch, capsys):
    logs = tmp_path / "logs"
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(logs))
    _run_demo()
    main(["run", "--repo", str(DEMO), "--issue", "nope", "--agent", "fake"])
    monkeypatch.setattr("verifix.cli.main.build_application", lambda a, e: SimpleNamespace(run=lambda repo, issue_id: 1 / 0))
    with pytest.raises(ZeroDivisionError):
        _run_demo()
    (logs / runlog.HOST_LOG).write_text(json.dumps({"type": "cli_exit", "data": {}}) + "\n" + json.dumps({"type": "apply_result", "data": {}}) + "\n")
    capsys.readouterr()

    assert main(["logs", "--dir", str(logs)]) == 0
    listing = capsys.readouterr().out
    assert "verified" in listing and "crashed" in listing and listing.count("\n") == 4  # header + 3 runs

    assert main(["logs", "--dir", str(logs), "--signal", "crashed"]) == 0
    assert capsys.readouterr().out.count("\n") == 2  # header + the one crashed run

    run_id = next(p for p in logs.glob("*.jsonl") if p.name != runlog.HOST_LOG).stem
    assert main(["logs", "--dir", str(logs), "--show", run_id[:15]]) in (0, 2)  # prefix may be ambiguous within one second
    capsys.readouterr()
    assert main(["logs", "--dir", str(logs), "--show", run_id]) == 0
    assert "log_start" in capsys.readouterr().out

    assert main(["logs", "--dir", str(logs), "--summary"]) == 0
    summary = capsys.readouterr().out
    assert "3 runs" in summary and "verified=1" in summary and "crashed=1" in summary
    assert "ZeroDivisionError" in summary and "Verifiers:" in summary and "security" in summary
    assert "nope" in summary and "cli_exit=1" in summary and "apply_result=1" in summary


def test_a_killed_run_leaves_a_readable_incomplete_log(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    (d / "20260101-000000-aaaaaa.jsonl").write_text(
        json.dumps({"v": 1, "ts": 1.0, "type": "log_start", "data": {"command": "run", "client": "cli", "argv": [], "git": ""}}) + '\n{"v": 1, "ts": 2.0, "ty')
    runs = runlog.load_runs(d)
    assert runs[0]["end"]["status"] == "incomplete" and "incomplete" in runlog.format_list(runs)
    assert "no runs logged" == runlog.format_list([])


def test_logging_is_off_for_read_only_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIX_LOG_DIR", str(tmp_path / "logs"))
    repo = tmp_path / "r"
    shutil.copytree(DEMO, repo)
    main(["logs", "--repo", str(repo)])
    assert not (tmp_path / "logs").exists()

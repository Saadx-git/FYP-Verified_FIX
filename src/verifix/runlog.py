"""Structured run logs: one JSONL file per CLI run, plus tools to find bugs and weak spots across runs.

What is written to `<repo>/.verifix/logs/<run_id>.jsonl` (override the folder with VERIFIX_LOG_DIR):
every harness event, every LLM call (purpose, model, tokens, latency, retries, errors, short previews),
handled errors, crashes with tracebacks, and a closing record with the outcome and automatic warning `signals`.
VERIFIX_LOG_CONTENT=off|preview|full controls how much prompt/response text is kept (default: 1500-char previews).
Secrets (API keys, bearer tokens) are redacted from every line.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Self

from verifix.events import emitter
from verifix.llm import client as llm_client

KEEP = int(os.environ.get("VERIFIX_LOG_KEEP", "300"))
PREVIEW = 1500
HOST_LOG = "extension.jsonl"
_SECRETS = re.compile(r"(gsk_\w{10,}|ghp_\w{10,}|github_pat_\w{10,}|(?i:bearer)\s+[\w.\-]{12,}|(?i:(?:GROQ_API_KEY|GITHUB_TOKEN)\s*[=:]\s*)\S+)")
ACTIVE: RunLog | None = None


def redact(text: str) -> str:
    return _SECRETS.sub("[REDACTED]", text)


def log_dir(base: str) -> Path:
    return Path(os.environ.get("VERIFIX_LOG_DIR") or Path(base) / ".verifix" / "logs")


def note_error(exc: BaseException | str) -> None:
    """Record a handled error (e.g. a bad API key) in the active run log, if there is one."""
    if ACTIVE:
        ACTIVE.write("error", {"message": str(exc), "type": type(exc).__name__ if not isinstance(exc, str) else "error"})


def compute_signals(events: list[tuple[str, dict]], status: str) -> list[str]:
    """Automatic warning signs worth a look: crashes, empty patches, disagreeing verifiers, flaky LLM calls..."""
    sig: set[str] = set()
    if status == "crashed":
        sig.add("crashed")
    by_patch: dict[str, dict[str, str]] = defaultdict(dict)
    diffs, max_attempts, final = [], 0, {}
    for kind, d in events:
        if kind == "verifier_finished":
            by_patch[d.get("patch_id", "")][d["verifier"]] = d["status"]
            if str(d.get("summary", "")).startswith("verifier crashed"):
                sig.add("verifier_crashed")
            if d["verifier"] == "patch" and d["status"] == "fail":
                sig.add("empty_patch")
        elif kind == "issue_unclear" or (kind == "issue_understood" and d.get("unclear")):
            sig.add("unclear_issue")
        elif kind == "llm_call":
            if d.get("error"):
                sig.add("llm_error")
            if d.get("retries"):
                sig.add("llm_retries")
        elif kind == "patch_generated":
            if diffs and diffs[-1] == d.get("diff"):
                sig.add("stuck")
            diffs.append(d.get("diff"))
        elif kind == "run_started":
            max_attempts = d.get("max_attempts", 0)
        elif kind == "run_finished":
            final = d
    for results in by_patch.values():  # the cheap tests and the independent checks should usually agree
        tests, others = results.get("unit_tests"), [results[v] for v in ("requirement", "reproduction") if v in results]
        if tests and others and ("fail" in others) != (tests == "fail"):
            sig.add("disagreement")
    if final.get("decision") == "reject":
        sig.add("rejected")
        if max_attempts and final.get("attempts") == max_attempts:
            sig.add("attempts_exhausted")
    return sorted(sig)


class RunLog:
    def __init__(self, directory: Path, command: str, argv: list[str]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.path = directory / f"{self.run_id}.jsonl"
        self.command, self.argv, self.exit_code = command, argv, None
        self.start, self.events, self.llm_calls = time.time(), [], []
        self._prune(directory)
        self._fh = self.path.open("a")

    @classmethod
    def start_for(cls, command: str, base: str, argv: list[str]) -> RunLog:
        return cls(log_dir(base), command, argv)

    def write(self, kind: str, data: dict[str, Any], ts: float | None = None) -> None:
        line = json.dumps({"v": 1, "ts": ts or time.time(), "type": kind, "data": data}, default=str)
        self._fh.write(redact(line) + "\n")
        self._fh.flush()

    def __enter__(self) -> Self:
        global ACTIVE
        ACTIVE = self
        emitter.SINKS.append(self._on_event)
        llm_client.OBSERVERS.append(self._on_llm)
        self.write("log_start", {
            "run_id": self.run_id, "command": self.command, "argv": self.argv, "cwd": os.getcwd(),
            "client": os.environ.get("VERIFIX_CLIENT", "cli"), "python": sys.version.split()[0], "platform": platform.platform(),
            "git": _git_sha(), "log_content": os.environ.get("VERIFIX_LOG_CONTENT", "preview")})
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        global ACTIVE
        emitter.SINKS.remove(self._on_event)
        llm_client.OBSERVERS.remove(self._on_llm)
        ACTIVE = None
        status = "completed"
        if exc_type is KeyboardInterrupt:
            status = "cancelled"
        elif exc is not None:
            status = "crashed"
            self.write("crash", {"type": exc_type.__name__, "message": str(exc), "traceback": "".join(traceback.format_exception(exc_type, exc, tb))})
        final = next((d for k, d in reversed(self.events) if k == "run_finished"), {})
        issue = next((d.get("issue_id") for k, d in self.events if k in ("issue_loaded", "issue_understood", "issue_unclear")), "")
        self.write("log_end", {
            "status": status, "exit_code": self.exit_code, "seconds": round(time.time() - self.start, 2), "issue_id": issue,
            "decision": final.get("decision", ""), "attempts": final.get("attempts", 0),
            "tokens": sum(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in self.llm_calls),
            "llm_calls": len(self.llm_calls), "signals": compute_signals([*self.events, *(("llm_call", c) for c in self.llm_calls)], status)})
        self._fh.close()
        return False  # never swallow the exception

    def _on_event(self, event: dict) -> None:
        self.events.append((event["type"], event["data"]))
        self.write(event["type"], event["data"], event["ts"])

    def _on_llm(self, rec: dict) -> None:
        mode = os.environ.get("VERIFIX_LOG_CONTENT", "preview")
        request, response = str(rec.pop("request", "") or ""), str(rec.pop("response", "") or "")
        if mode != "off":
            cut = (lambda t: t) if mode == "full" else (lambda t: t[:PREVIEW] + (f"... [{len(t) - PREVIEW} more chars]" if len(t) > PREVIEW else ""))
            rec["request_preview"], rec["response_preview"] = cut(request), cut(response)
        rec["seconds"] = round(rec["seconds"], 2)
        self.llm_calls.append(rec)
        self.write("llm_call", rec)

    @staticmethod
    def _prune(directory: Path) -> None:
        old = sorted(p for p in directory.glob("*.jsonl") if p.name != HOST_LOG)
        for p in old[: max(len(old) - KEEP + 1, 0)]:
            p.unlink(missing_ok=True)


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=3, check=False)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------- reading and analysing logs

def load_runs(directory: Path) -> list[dict]:
    runs = []
    for path in sorted(p for p in directory.glob("*.jsonl") if p.name != HOST_LOG):
        recs = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn last line from a killed process
        if not recs:
            continue
        end = next((r["data"] for r in reversed(recs) if r["type"] == "log_end"), None)
        runs.append({"id": path.stem, "path": path, "recs": recs, "meta": recs[0]["data"] if recs[0]["type"] == "log_start" else {},
                     "end": end or {"status": "incomplete", "signals": ["incomplete"]}})
    return runs


def format_list(runs: list[dict], last: int = 20, signal: str = "") -> str:
    rows = [r for r in runs if not signal or signal in r["end"].get("signals", [])][-last:]
    out = [f"{'run id':<24}{'cmd':<11}{'client':<8}{'status':<10}{'decision':<22}{'att':>3}{'tokens':>8}{'secs':>7}  signals"]
    for r in rows:
        e, m = r["end"], r["meta"]
        out.append(f"{r['id']:<24}{m.get('command', '?'):<11}{m.get('client', '?'):<8}{e.get('status', '?'):<10}{e.get('decision', '') or '-':<22}"
                   f"{e.get('attempts', 0):>3}{e.get('tokens', 0):>8}{e.get('seconds', 0):>7}  {','.join(e.get('signals', [])) or '-'}")
    return "\n".join(out) if rows else "no runs logged"


def format_show(run: dict) -> str:
    t0 = run["recs"][0]["ts"]
    out = [f"{run['id']}  ({run['path']})"]
    for r in run["recs"]:
        k, d, at = r["type"], r["data"], f"+{r['ts'] - t0:6.2f}s"
        if k == "log_start":
            line = f"{d['command']} client={d['client']} git={d['git'] or '?'} argv={' '.join(d['argv'])}"
        elif k == "llm_call":
            line = (f"{d['purpose'] or '?'} {d['model']} {d.get('prompt_tokens', 0)}+{d.get('completion_tokens', 0)} tok {d['seconds']}s"
                    + (" cached" if d.get("cached") else "") + (f" retries={d['retries']}" if d.get("retries") else "")
                    + (f" ERROR {d['error']}" if d.get("error") else "") + (f" tools={','.join(d['tool_calls'])}" if d.get("tool_calls") else ""))
        elif k == "verifier_finished":
            line = f"{d['verifier']} -> {d['status']}  {str(d.get('summary', ''))[:90]}"
        elif k == "patch_generated":
            line = f"attempt {d['attempt']} files={d['files']}"
        elif k in ("decision", "run_finished"):
            line = f"{d.get('decision')} {d.get('rationale', '')[:80]}"
        elif k == "crash":
            line = f"{d['type']}: {d['message']}\n{d['traceback']}"
        elif k == "error":
            line = d["message"]
        elif k == "log_end":
            line = f"{d['status']} exit={d['exit_code']} {d['seconds']}s tokens={d['tokens']} signals={d['signals']}"
        else:
            line = ", ".join(f"{a}={str(b)[:40]}" for a, b in list(d.items())[:3])
        out.append(f"{at}  {k:<18}{line}")
    return "\n".join(out)


def summarize(runs: list[dict], host_log: Path | None = None) -> str:
    if not runs:
        return "no runs logged"
    ends = [r["end"] for r in runs]
    decisions = Counter(e.get("decision") or e.get("status", "?") for e in ends)
    signals = Counter(s for e in ends for s in e.get("signals", []))
    out = [f"{len(runs)} runs ({runs[0]['id'][:8]} .. {runs[-1]['id'][:8]})",
           "outcomes : " + ", ".join(f"{k}={v}" for k, v in decisions.most_common()),
           "signals  : " + (", ".join(f"{k}={v}" for k, v in signals.most_common()) or "none"),
           (f"tokens   : {sum(e.get('tokens', 0) for e in ends)} total, "
            f"{sum(e.get('tokens', 0) for e in ends) // max(len(runs), 1)} per run; attempts avg {sum(e.get('attempts', 0) for e in ends) / len(runs):.1f}")]
    llm: dict[tuple[str, str], list[dict]] = defaultdict(list)
    ver: dict[str, list[dict]] = defaultdict(list)
    crashes: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for r in runs:
        for rec in r["recs"]:
            d = rec["data"]
            if rec["type"] == "llm_call":
                llm[(d.get("purpose") or "?", d["model"])].append(d)
            elif rec["type"] == "verifier_finished":
                ver[d["verifier"]].append(d)
            elif rec["type"] == "crash":
                crashes[f"{d['type']}: {d['message'].splitlines()[0][:100] if d['message'] else ''}"] += 1
            elif rec["type"] == "error":
                errors[d["message"].splitlines()[0][:110]] += 1
    if llm:
        out.append("\nLLM calls (purpose, model): calls  errors  retries  avg s  cache%  tokens")
        for (purpose, model), cs in sorted(llm.items()):
            out.append(f"  {purpose:<14}{model:<24}{len(cs):>5}{sum(1 for c in cs if c.get('error')):>7}{sum(c.get('retries', 0) for c in cs):>8}"
                       f"{sum(c['seconds'] for c in cs) / len(cs):>7.1f}{100 * sum(1 for c in cs if c.get('cached')) // len(cs):>7}%"
                       f"{sum(c.get('prompt_tokens', 0) + c.get('completion_tokens', 0) for c in cs):>9}")
    if ver:
        out.append("\nVerifiers: runs  fail%  avg s  crashed/uncertain")
        for name, vs in sorted(ver.items()):
            out.append(f"  {name:<18}{len(vs):>5}{100 * sum(1 for v in vs if v['status'] == 'fail') // len(vs):>6}%"
                       f"{sum(v.get('duration', 0) or 0 for v in vs) / len(vs):>7.1f}{sum(1 for v in vs if v['status'] == 'uncertain'):>8}")
    for title, counter in (("Crashes", crashes), ("Handled errors", errors)):
        if counter:
            out.append(f"\n{title}:")
            out += [f"  {n}x {msg}" for msg, n in counter.most_common(8)]
    if host_log and host_log.is_file():
        host = Counter(json.loads(line)["type"] for line in host_log.read_text().splitlines() if line.strip().startswith("{"))
        out.append("\nVS Code extension host: " + ", ".join(f"{k}={v}" for k, v in host.most_common()))
    return "\n".join(out)

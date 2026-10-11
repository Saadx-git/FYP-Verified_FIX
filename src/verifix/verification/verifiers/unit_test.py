from __future__ import annotations

import re
import sys
from pathlib import Path

from verifix.models.evidence import (
    Evidence,
    TestOutcome,
    VerificationFinding,
    VerificationResult,
    VerificationStatus,
)
from verifix.sandbox.base import ExecutionRequest, ResourceLimits
from verifix.verification.base import VerificationContext, Verifier

_LINE = re.compile(r"^(PASSED|FAILED|ERROR)\s+(\S+)")
_SUMMARY = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS)\s+(\S+)(?: - (.*))?$")
_DURATION = re.compile(r"^\s*([\d.]+)s\s+call\s+(\S+)")
_SECTION = re.compile(r"^_{3,} (.+?) _{3,}$")
_OUTCOME = {"PASSED": "passed", "FAILED": "failed", "ERROR": "error", "XFAIL": "xfailed", "XPASS": "xpassed"}
MAX_FAILED, MAX_PASSED, MAX_MESSAGE = 200, 300, 1500


class UnitTestVerifier(Verifier):
    """Runs pytest on the patched repo; target tests must pass, others must not regress."""

    name = "unit_tests"

    def verify(self, context: VerificationContext) -> VerificationResult:
        issue = context.issue
        command = issue.test_command or [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider"]
        if not issue.test_command and Path(context.repo_path, "tests/integration").is_dir():
            command += ["--ignore=tests/integration"]
        command = pytest_cmd(command)
        res = context.sandbox.execute(
            ExecutionRequest(
                command=command, repo_path=context.repo_path,
                patch_diff=context.patch.diff, limits=ResourceLimits(timeout_seconds=120),
            )
        )
        evidence = [Evidence(source=self.name, kind="pytest_output", content=res.stdout[-4000:])]
        if res.timed_out or "patch failed to apply" in res.stderr:
            msg = "tests timed out" if res.timed_out else res.stderr.strip()
            return VerificationResult(
                self.name, VerificationStatus.FAIL, 1.0,
                [VerificationFinding(msg, "error")], evidence, 0.0, res.duration_seconds,
            )

        outcomes = parse_outcomes(res.stdout)
        tests, omitted = collect_tests(res.stdout, issue.fail_to_pass, issue.pass_to_pass)
        passed = [t for t, o in outcomes.items() if o == "PASSED"]
        failed = [t for t, o in outcomes.items() if o != "PASSED"]
        findings: list[VerificationFinding] = []
        for t in failed:
            kind = "target test still failing" if _matches(t, issue.fail_to_pass) else (
                "regression" if _matches(t, issue.pass_to_pass) else "test failure"
            )
            findings.append(VerificationFinding(f"{kind}: {t}", "error", t))
        missing = [t for t in issue.fail_to_pass if not _matches_any(t, outcomes)]
        for t in missing:
            findings.append(VerificationFinding(f"target test not run: {t}", "error", t))
        if not outcomes:
            findings.append(VerificationFinding(f"no tests collected (exit {res.exit_code})", "error"))
        if omitted:
            findings.append(VerificationFinding(f"{omitted} more passed tests not listed", "info"))
        if any(f.severity == "error" for f in findings):
            return VerificationResult(
                self.name, VerificationStatus.FAIL, 1.0, findings, evidence, 0.0, res.duration_seconds, tests
            )
        return VerificationResult(
            self.name, VerificationStatus.PASS, 1.0,
            [VerificationFinding(f"{len(passed)} passed", "info"), *findings], evidence, 0.0, res.duration_seconds, tests,
        )


def parse_outcomes(stdout: str) -> dict[str, str]:
    """Map pytest `-rA` summary lines to {test_id: PASSED|FAILED|ERROR}."""
    return {m[2]: m[1] for line in stdout.splitlines() if (m := _LINE.match(line))}


def pytest_cmd(command: list[str]) -> list[str]:
    """Ask pytest for per-test durations (only when the command is pytest; other runners are left alone)."""
    if any("pytest" in part for part in command) and "--durations=0" not in command:
        return [*command, "--durations=0", "--durations-min=0"]
    return command


def parse_tests(stdout: str, fail_to_pass: list[str] = (), pass_to_pass: list[str] = (), role: str = "") -> list[TestOutcome]:
    """Per-test results from pytest `-rA` output: outcome, duration, failure excerpt, and why the test matters."""
    durations = {m[2]: float(m[1]) for line in stdout.splitlines() if (m := _DURATION.match(line))}
    sections: dict[str, str] = {}
    name, buf = "", []
    for line in stdout.splitlines():
        if m := _SECTION.match(line):
            if name:
                sections[name] = "\n".join(buf)
            name, buf = m[1], []
        elif name and line.startswith("====="):
            sections[name] = "\n".join(buf)
            name, buf = "", []
        elif name:
            buf.append(line)
    if name:
        sections[name] = "\n".join(buf)
    tests = []
    for line in stdout.splitlines():
        if not (m := _SUMMARY.match(line)):
            continue
        kind, test_id, short = m[1], m[2], m[3] or ""
        outcome = _OUTCOME[kind]
        message = ""
        if outcome in ("failed", "error"):
            short_name = test_id.split("::")[-1].split("[")[0]
            trace = next((t for n, t in sections.items() if n.split(".")[-1].split("[")[0] == short_name), "")
            message = (trace.strip() or short)[-MAX_MESSAGE:]
        tests.append(TestOutcome(
            test_id, outcome,
            role or ("fail_to_pass" if _matches(test_id, list(fail_to_pass)) else
                     "pass_to_pass" if _matches(test_id, list(pass_to_pass)) else "other"),
            durations.get(test_id), message))
    return tests


def collect_tests(stdout: str, fail_to_pass=(), pass_to_pass=(), role: str = "") -> tuple[list[TestOutcome], int]:
    """parse_tests with size caps: failures first (up to 200), then passes (up to 300); returns (tests, omitted passes)."""
    tests = parse_tests(stdout, fail_to_pass, pass_to_pass, role)
    bad = [t for t in tests if t.outcome in ("failed", "error")][:MAX_FAILED]
    good = [t for t in tests if t.outcome not in ("failed", "error")]
    return bad + good[:MAX_PASSED], max(len(good) - MAX_PASSED, 0)


def _matches(test_id: str, wanted: list[str]) -> bool:
    return any(test_id == w or test_id.endswith(w) or w in test_id for w in wanted)


def _matches_any(wanted: str, outcomes: dict[str, str]) -> bool:
    return any(t == wanted or t.endswith(wanted) or wanted in t for t in outcomes)

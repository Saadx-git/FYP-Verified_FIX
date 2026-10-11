from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from verifix.agent.base import AgentRequest, AgentResponse, CodingAgent
from verifix.llm.client import GroqClient
from verifix.models.patch import CandidatePatch, PatchMetadata, RepairPlan
from verifix.patching.diff import parse_changed_files
from verifix.repository.context_retriever import ContextRetriever
from verifix.repository.dependency_analyzer import DependencyAnalyzer
from verifix.repository.file_inspector import FileInspector
from verifix.repository.symbol_searcher import SymbolSearcher

_IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".verifix")
_MAX_OBS = 3000
# strategies whose next attempt starts from the previous patch (others start from the original files)
BUILD_ON_PREVIOUS = {"revise_patch", "address_security"}

SYSTEM = (
    "You are a careful software engineer fixing a bug in a Python repository. Work in small steps: "
    "locate the relevant code yourself with search/find_symbol/list_dir/read_file before editing (the fix may span "
    "several files), make the minimal correct fix with edit_file, then call submit. "
    "Do not use eval/exec or other unsafe constructs. Do not edit tests."
)

TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read numbered lines of a file.", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search", "description": "Regex search over repo text files; returns path:line matches. Optional path prefix narrows the search.", "parameters": {
        "type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "list_dir", "description": "List the entries of a directory (use '.' for the repo root).", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "find_symbol", "description": "Find function/class definitions by (partial) name.", "parameters": {
        "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace one exact, unique occurrence of old with new in a file.", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {"name": "submit", "description": "Finish. Give a short plan/summary of the fix and your confidence 0-1.", "parameters": {
        "type": "object", "properties": {"summary": {"type": "string"}, "confidence": {"type": "number"}}, "required": ["summary"]}}},
]


class GroqAgent(CodingAgent):
    """Small tool-loop coding agent on Groq. Edits a scratch copy; the diff is the patch."""

    def __init__(self, client: GroqClient, model: str, max_steps: int = 16) -> None:
        self.client, self.model, self.max_steps = client, model, max_steps

    def generate_patch(self, request: AgentRequest) -> AgentResponse:
        with tempfile.TemporaryDirectory(prefix="verifix-agent-") as tmp:
            work = Path(tmp) / "repo"
            shutil.copytree(request.repo_path, work, ignore=_IGNORE)
            self._git(work, "init", "-q")
            self._git(work, "add", "-A")
            self._git(work, "-c", "user.name=v", "-c", "user.email=v@v", "commit", "-q", "-m", "base", "--allow-empty")
            strategy = request.context.get("strategy", "")
            previous = request.context.get("previous_diff", "")
            built_on_previous = False
            if previous and strategy in BUILD_ON_PREVIOUS:  # revise: the earlier patch is already in the files
                applied = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=previous, cwd=work,
                                         text=True, capture_output=True, check=False)
                built_on_previous = applied.returncode == 0
            prompt = self._prompt(request, work, built_on_previous)
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
            tokens, summary, confidence = 0, "", 0.5
            for _ in range(self.max_steps):
                resp = self.client.chat(self.model, messages, tools=TOOLS, max_tokens=4096, reasoning_effort="low")
                tokens += resp.tokens
                messages.append(resp.message or {"role": "assistant", "content": resp.text})
                if not resp.tool_calls:
                    summary = summary or resp.text.strip()[:300]
                    break
                done = False
                for call in resp.tool_calls:
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if name == "submit":
                        summary, confidence, done = args.get("summary", ""), float(args.get("confidence", 0.5)), True
                        obs = "submitted"
                    else:
                        obs = self._tool(work, name, args)
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": obs[:_MAX_OBS]})
                if done:
                    break
            self._git(work, "add", "-A")
            diff = self._git(work, "diff", "--cached", "--no-color").stdout
        plan = RepairPlan(summary=summary or "no summary", target_files=[f.path for f in parse_changed_files(diff)])
        patch = CandidatePatch(diff=diff, plan=plan, metadata=PatchMetadata(
            agent_name=f"groq:{self.model}", agent_confidence=confidence, tokens_used=tokens))
        return AgentResponse(patch=patch, plan=plan, raw_output=summary)

    def _prompt(self, req: AgentRequest, work: Path, built_on_previous: bool) -> str:
        issue = req.issue
        # when a previous patch is applied, describe the code as it is now, not as in the original repo
        ctx = ContextRetriever().retrieve(str(work if built_on_previous else req.repo_path), issue)
        parts = [f"Issue #{issue.issue_id}: {issue.title}\n{issue.body}"]
        if issue.acceptance_criteria:
            parts.append("Acceptance criteria:\n- " + "\n- ".join(issue.acceptance_criteria))
        if issue.requirements:
            parts.append("Requirements:\n" + "\n".join(f"- {r.description}: expected {r.expected_behavior}" for r in issue.requirements))
        if issue.fail_to_pass:
            parts.append("Tests that must pass after the fix: " + ", ".join(issue.fail_to_pass))
        parts.append("Repository map:\n" + ctx["repo_map"])
        if ctx["candidates"]:
            parts.append("Possibly relevant locations (may be incomplete or wrong; the fix may span several files):\n- "
                         + "\n- ".join(ctx["candidates"]) + ("\nSymbols: " + "; ".join(ctx["symbols"]) if ctx["symbols"] else ""))
        if req.feedback:
            strategy, previous = req.context.get("strategy", ""), req.context.get("previous_diff", "")
            parts.append("Your previous attempt FAILED verification.\nFeedback: " + req.feedback.summary
                         + "\n" + "\n".join(req.feedback.details))
            if built_on_previous:
                parts.append("Your previous patch (already applied):\n" + previous[:3000])
                parts.append("Your previous patch is ALREADY APPLIED to the files you can read. Make the smallest further "
                             "change that fixes the problem above. Do not start over or undo working parts."
                             + (" Remove the unsafe construct but keep the behaviour." if strategy == "address_security" else ""))
            elif strategy == "regenerate_patch":
                parts.append("Discard your earlier approach entirely and solve the issue a different way. "
                             "(The earlier diff is intentionally not shown so you do not anchor on it.)")
            elif strategy == "fix_environment":
                parts.append("The patch could not be applied or run. Produce a clean, minimal diff against the original files.")
            else:  # reexplore_repository, or no strategy given: show the failed diff
                if previous:
                    parts.append("Previous diff (do not repeat its mistake):\n" + previous[:3000])
                if strategy == "reexplore_repository":
                    changed = [f.path for f in parse_changed_files(previous)][:3]
                    graph = DependencyAnalyzer().analyze(req.repo_path) if changed else {}
                    users = sorted({f for f, deps in graph.items() for c in changed if c in deps})[:8]
                    parts.append("Re-explore the repository before editing; your earlier approach did not work. Read more of the "
                                 "relevant code first (search and read at least two files you have not looked at)."
                                 + (f" Files that import {', '.join(changed)}: {', '.join(users)}." if users else ""))
        return "\n\n".join(parts)

    def _tool(self, work: Path, name: str, args: dict) -> str:
        try:
            if name == "read_file":
                return FileInspector().read_file(str(self._safe(work, args["path"])), int(args.get("start", 1)), args.get("end"))
            if name == "search":
                return "\n".join(SymbolSearcher().grep(str(work), args["pattern"], prefix=args.get("path", ""))) or "no matches"
            if name == "list_dir":
                entries = sorted(f"{e.name}/" if e.is_dir() else e.name for e in self._safe(work, args.get("path", ".") or ".").iterdir()
                                 if e.name != ".git")
                return "\n".join(entries[:100]) + (f"\n... ({len(entries) - 100} more)" if len(entries) > 100 else "")
            if name == "find_symbol":
                return "\n".join(SymbolSearcher().find_symbol(str(work), args["name"])) or "no matches"
            if name == "edit_file":
                path = self._safe(work, args["path"])
                text = path.read_text()
                if not args["old"]:
                    return "error: 'old' must not be empty"
                if text.count(args["old"]) != 1:
                    return f"error: 'old' must match exactly once (found {text.count(args['old'])})"
                path.write_text(text.replace(args["old"], args["new"]))
                return "ok"
            return f"error: unknown tool {name}"
        except (KeyError, OSError, ValueError, re.error) as exc:
            return f"error: {exc}"

    @staticmethod
    def _safe(work: Path, rel: str) -> Path:
        path = (work / rel).resolve()
        if path != work.resolve() and work.resolve() not in path.parents:
            raise ValueError("path outside repository")
        return path

    @staticmethod
    def _git(work: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=work, capture_output=True, text=True, check=False)

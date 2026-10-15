# Verifix — a verification-centered agent harness

Verifix treats an AI coding agent as an **untrusted** patch generator. The agent proposes a fix; an independent
harness gathers evidence, fuses it into a decision, diagnoses failures, and decides whether to retry or stop.

```
issue → agent → patch → [unit tests · static analysis · security · reproduction test · integration · requirement · LLM review]
      → evidence fusion → VERIFIED | REPAIR | REJECT → diagnosis → strategy selector → next patch → …
```

A VERIFIED result is an evidence-based assessment, not a proof of correctness.

## Quick start
```bash
uv sync
echo 'GROQ_API_KEY=...' > .env          # gitignored; GITHUB_TOKEN is optional (private repos)
uv run pytest                           # 27 tests, no network needed except container image pull

# fix a bug described in plain English (an issue file is created for you)
uv run verifix run --repo path/to/python/repo --description "apply_discount returns the discount, not the price"
# or a GitHub issue
uv run verifix run --repo path/to/repo --issue https://github.com/owner/repo/issues/12
# verify a patch you already have (exit code 0 only if VERIFIED)
uv run verifix verify --repo path/to/repo --patch change.diff --description "what it should fix"
# interpret an issue without running anything (what the sidebar shows for confirmation)
uv run verifix understand --repo path/to/repo --description "..."
# apply a run's patch (a verified one freely; an unverified one only with --force, after it lists what failed)
uv run verifix apply --repo path/to/repo [--force]
# render / list results
uv run verifix report --repo path/to/repo --list
uv run verifix report --input report.json --out report.html
# benchmark: baselines A–C, full system, ablations A–F (see tests/fixtures/dataset.json for the format)
uv run verifix evaluate --dataset tests/fixtures/dataset.json --config all --agent groq --out results.json
```
Useful flags: `--sandbox container` (rootless podman/docker, no network), `--verifiers a,b,c`, `--max-attempts N`,
`--feedback targeted|raw`, `--stopping adaptive|fixed`, `--events jsonl` (machine-readable stream).

## VS Code extension
```bash
cd extension && npm install && npm run build && npm test   # npm test checks Apply Patch against a mocked VS Code API
```
Open this repo in VS Code and press **F5**. The default configs use the **live Groq agent** (`discount` and `clamp` repos, no planned failures).
Each launch config opens a fresh throwaway copy under `.workspaces/` (gitignored), so Apply Patch never modifies the tracked sample repos.
A separate, clearly marked **DEMO ONLY** config (`tests/fixtures/demo-retry`) replays canned patches, including a planned bad first attempt, to show the retry flow; the sidebar shows a DEMO MODE banner there. In the Verifix sidebar pick **＋ New issue…**, describe the bug or paste a GitHub link,
and press Run. Settings: `verifix.command`, `verifix.projectDir`, `verifix.agent` (groq|fake), `verifix.sandbox`, `verifix.maxAttempts`.

## GitHub Action
`.github/actions/verifix/action.yml` verifies a PR's diff against its base tree and fails the check unless VERIFIED.
See `docs/verifix-pr.example.yml`.

## Layout (`src/verifix`)
| Package | Role |
|---|---|
| `agent/` | `CodingAgent` interface; `GroqAgent` (tool-loop on Groq, edits a scratch copy), `FakeAgent` (canned diffs) |
| `issue/` | free text / GitHub URL → structured issue (LLM understanding), cached in `.verifix/issues/` |
| `repository/` | file listing, AST symbol search, grep, import graph, context retrieval |
| `sandbox/` | `LocalSandbox` (temp copy), `DockerSandbox` (rootless container, no network, limits) |
| `verification/` | orchestrator + registry + 8 verifiers (`verifiers/`); expensive ones skipped after a cheap failure |
| `evidence/` | in-memory store; rule-based fusion + reliability score |
| `diagnosis/`, `feedback/` | failure classification → targeted (or raw) feedback for the agent |
| `strategy/`, `control/` | repair/verification strategy selection, budget tracking, cost-aware stopping |
| `patching/` | diff parsing, ranking of attempts |
| `evaluation/` | oracle ground truth (held-out tests), metrics, baselines, ablations |
| `reporting/`, `store/` | JSON / text / HTML reports; SQLite run history (`.verifix/runs.db`) |
| `llm/`, `events/` | Groq client (cache, retry, token accounting); JSONL event stream used by the extension |

## How blame is assigned
Unit tests are compared with a baseline run of the **unpatched** repo. A test that already failed before the patch is reported as a
*pre-existing failure* (shown, never held against the patch); a test that passed before and fails now is a *regression*. The agent may
not edit test files (the edit tool refuses), and a patch that modifies existing tests is flagged. If a run ends **not verified**, the
sidebar lists exactly which checks failed and offers **Apply best patch anyway** (a modal confirmation first; `verifix apply --force` on
the CLI). An LLM/API error inside one attempt is recorded in that attempt instead of ending the run. The generated reproduction test is the least-trusted evidence (a model writes it from the issue text): it is told to assert only what the report states, and if it is the *only* failing check while the requirement check and the project's own tests pass, the run is VERIFIED with a visible warning instead of being rejected. Cancelling a run (SIGTERM) is logged as `cancelled`; the sidebar shows each agent step and any rate-limit wait.

## Run logs (finding bugs from real use)
Every `run`, `verify`, `understand` and `evaluate` writes `<repo>/.verifix/logs/<run_id>.jsonl` (override the folder with `VERIFIX_LOG_DIR`):
all harness events, every LLM call (purpose, model, tokens, latency, retries, errors, 1500-char previews), handled errors, crashes with
tracebacks, and a closing record with the outcome and automatic **signals** (`crashed`, `verifier_crashed`, `empty_patch`, `unclear_issue`,
`disagreement` between tests and the independent checks, `stuck`, `llm_error`, `llm_retries`, `rejected`, `attempts_exhausted`).
The VS Code extension adds `extension.jsonl` (CLI starts/exits, spawn failures, Apply Patch results, sidebar script errors); command
**Verifix: Open Latest Run Log**.
```bash
uv run verifix logs --repo <repo>                 # recent runs with decision, tokens, signals
uv run verifix logs --repo <repo> --signal crashed
uv run verifix logs --repo <repo> --show <run_id> # timeline of one run
uv run verifix logs --repo <repo> --summary       # outcomes, signals, LLM + verifier stats, crash groups
```
`VERIFIX_LOG_CONTENT=off|preview|full` sets how much prompt/response text is kept (default preview). API keys and tokens are redacted from
every line, but previews can contain code and issue text, so treat log folders as private. The newest 300 runs are kept (`VERIFIX_LOG_KEEP`).
A logging failure never stops a run.

## Known limitations
- Typed issues are interpreted by an LLM against an outline of the repo: typos are mapped to real names, but a vague or unrelated report can be force-fitted onto the closest function. The sidebar shows the interpretation for confirmation before anything runs; read it before pressing Run.
- Python repositories only. Dependencies of the target repo are not installed automatically (container `install=True` exists but is not exposed yet).
- LLM verifiers (requirement, review, reproduction) can be wrong either way; the review is advisory by design. Measure false rejection with `evaluate`.
- Diagnosis is rule-based; semgrep is not implemented; mutation testing is a lightweight opt-in verifier (`--verifiers …,mutation`); the bundled benchmark is a 2-instance toy, not SWE-bench.

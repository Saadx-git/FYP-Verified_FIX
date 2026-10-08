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
cd extension && npm install && npm run build
```
Open this repo in VS Code and press **F5** (two launch configs: canned-agent demo on `tests/fixtures/discount`, and the live
Groq agent on `tests/fixtures/clamp`). In the Verifix sidebar pick **＋ New issue…**, describe the bug or paste a GitHub link,
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

## Known limitations
- Python repositories only. Dependencies of the target repo are not installed automatically (container `install=True` exists but is not exposed yet).
- LLM verifiers (requirement, review, reproduction) can be wrong either way; the review is advisory by design. Measure false rejection with `evaluate`.
- Diagnosis is rule-based; semgrep is not implemented; mutation testing is a lightweight opt-in verifier (`--verifiers …,mutation`); the bundled benchmark is a 2-instance toy, not SWE-bench.

# Claude Harness

A spec-driven code generation harness for Claude Code. You describe what to build; the harness writes, validates, and repairs the implementation automatically — no API key required.

---

## How it works

You write a **spec** that describes an interface contract. The harness:

1. Loads the spec and reads the relevant source files into context
2. Generates an implementation and test suite
3. Runs a language-appropriate gate suite (type-checker → linter → security scanner → tests)
4. Repairs the implementation against gate errors, guided by memory of past failures
5. Either delivers a passing artifact or escalates for human review

Claude Code is the orchestrator. The harness provides tools for gate execution, file I/O, and failure memory — no separate LLM calls, no API key.

---

## Setup

```bash
bash /path/to/harness-no-api-key/setup.sh [project-dir]
```

This installs the slash commands under `.claude/commands/harness/` and registers the MCP server in `.mcp.json`. Then open Claude Code in the project and run:

```
/harness:init
```

---

## Configuration

After `/harness:init`, edit `.harness/config.py`:

```python
LANGUAGE = "python"     # python | typescript | go | rust
PROJECT_ROOT = "."      # root used for file resolution and PYTHONPATH
MAX_REPAIR_ATTEMPTS = 3 # how many times to retry before escalating
```

---

## Commands

### `/harness:init`

Initialize the harness in the current project.

Creates the `.harness/` directory structure and writes a default `config.py`. Run once per project.

```
.harness/
├── specs/        ← spec files
├── tasks/        ← multi-spec task DAGs
├── results/      ← run artifacts (implementation + gate results)
└── checkpoints/  ← task resume state
```

---

### `/harness:write-spec <description>`

**Write a spec (or full task DAG) for a piece of work.**

Claude explores the codebase — finding the entry point, tracing dependencies, identifying conventions — then assesses scope and chooses a path:

- **Single spec** — one coherent, independently testable unit: one class, one module, one function group. Produces `.harness/specs/<id>.py`.
- **Task (multi-spec DAG)** — work that spans multiple modules with one-way dependencies, where a later piece can't be tested without a prior piece existing. Produces multiple spec files and a `.harness/tasks/<id>.py` DAG.

Claude tells you which path it chose and why before writing anything.

```
/harness:write-spec add a rate-limiter middleware to the API router
/harness:write-spec add OAuth2 login with session management
```

**Single spec output:** `.harness/specs/<id>.py` — then run `/harness:build <id>`.  
**Task output:** `.harness/specs/<id>.py` × N and `.harness/tasks/<id>.py` — then run `/harness:build <task-id>`.

---

### `/harness:build <spec-id | task-id>`

**Generate, validate, and repair an implementation. Works for both single specs and multi-spec tasks.**

Pass either a spec ID or a task ID — the harness detects which file exists under `.harness/specs/` or `.harness/tasks/` and routes accordingly.

```
/harness:build auth-session        ← single spec
/harness:build oauth2-login        ← task DAG
```

#### Single spec flow

1. Loads the spec and fetches reference files into context
2. Generates implementation + tests
3. Runs the gate suite for the configured language
4. If gates fail: retrieves similar past failures from memory, diagnoses root cause, generates a minimal diff, and re-runs
5. Repeats up to `MAX_REPAIR_ATTEMPTS` times
6. On success → tells you to run `/harness:deliver <run-id>`
7. On escalation → tells you to run `/harness:debug`

**Gate suites by language:**

| Language | Gates (in order) |
|---|---|
| Python | syntax → mypy → ruff → bandit → pytest |
| TypeScript | tsc → eslint → jest |
| Go | build → vet → staticcheck → test |
| Rust | check → clippy → test |

Gates fail fast — the first failure stops the run so Claude can repair the specific error before re-running everything.

#### Task flow

1. Loads the DAG and groups specs into layers (specs with the same dependency depth run in a layer)
2. Reads the checkpoint — skips specs that already passed in a previous run
3. Executes each spec in isolation via the spec flow above, injecting upstream implementations as context for downstream specs
4. Checkpoints after each pass so the task can resume if interrupted
5. Reports a table of results: ✓ passed / ⚠ escalated / ⊘ blocked

Blocked specs are specs whose upstream dependency escalated — they are skipped automatically and marked blocked in the report.

**Context tip:** Each spec adds to the session context. For tasks with 4+ specs, consider running `/compact` between layers or `/clear` + re-running `/harness:build` (the checkpoint resumes where you left off).

---

### `/harness:deliver [run-id]`

**Write a passing implementation to its target file.**

```
/harness:deliver auth-session-20240115-143022
```

If no `run-id` is given, uses the most recent passed run. Reads the artifact, loads the spec to find `target_file`, and writes the implementation. If the target file already exists with other content, integrates intelligently rather than overwriting.

Also writes the test file alongside the implementation (e.g., `tests/test_auth_session.py`).

Suggests reviewing the diff and committing:
```bash
git commit -m "feat: <spec description>"
```

---

### `/harness:debug [run-id]`

**Classify and explain an escalated run.**

```
/harness:debug auth-session-20240115-143022
```

If no `run-id` is given, uses the most recent escalated run. Reads the full attempt history and classifies the failure:

| Class | Diagnosis | Resolution |
|---|---|---|
| A | Spec ambiguity — description/criteria weren't precise enough | Proposes spec edits; offers to re-run |
| B | Missing context — wrong or missing `reference_files` | Proposes adding correct files; offers to re-run |
| C | Environment gap — required tool not installed | Gives install instructions |
| D | Test design flaw — tests coupled to implementation internals | Proposes revised tests; offers to re-run |
| E | Genuine hard problem — automation couldn't bridge the gap | Provides partial implementation and explains what's left |

---

### `/harness:status`

**Show recent runs.**

```
/harness:status
```

Lists passed and escalated runs with spec ID, timestamp, and (for escalated) which gate failed. Reminds you to run `/harness:deliver` or `/harness:debug` as appropriate.

---

## Typical workflows

### Single feature

```
/harness:write-spec add CSV export to the billing report
/harness:build billing-csv-export
/harness:deliver
```

### Multi-spec feature

```
/harness:write-spec add webhook delivery with retry and signing
/harness:build webhook-delivery

# if anything escalated:
/harness:debug

# when all pass:
/harness:deliver webhook-delivery-spec-a-<run-id>
/harness:deliver webhook-delivery-spec-b-<run-id>
```

### Resume interrupted task

```
# task was interrupted mid-run — checkpoint saved progress
/harness:build webhook-delivery
# ✓ already passed: webhook-model, webhook-sender
# running: webhook-retry ...
```

---

## Directory reference

```
.harness/
├── config.py                    ← LANGUAGE, PROJECT_ROOT, MAX_REPAIR_ATTEMPTS
├── specs/
│   └── <spec-id>.py             ← one spec per file
├── tasks/
│   └── <task-id>.py             ← DAG of specs
├── results/
│   └── <spec-id>-<timestamp>.json  ← full run artifact
└── checkpoints/
    └── <task-id>.json           ← list of completed spec IDs
```

Run artifacts store the full history: implementation at each attempt, gate results per attempt, final outcome (`passed` or `escalated`). `/harness:debug` reads these to diagnose failures.

---

## System tool requirements

The harness invokes these tools as subprocesses. Install what you need for your language:

| Language | Required |
|---|---|
| Python | `python`, `mypy`, `ruff`, `bandit`, `pytest` |
| TypeScript | `node`, `tsc`, `eslint`, `jest` (via npx) |
| Go | `go`, `staticcheck` |
| Rust | `cargo` |

Missing tools are skipped gracefully — the gate is omitted from the run rather than failing.

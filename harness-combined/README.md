# harness-combined

A unified Claude Code harness that combines two complementary systems:

- **Structured execution engine** — polyglot gate pipeline (lint → type-check → tests → security), diff-based repair loop, and BM25 failure memory from `harness-no-api-key`
- **SDLC workflow** — two-checkpoint feature pipeline (problem → design → TDD → critic review → merge), preventive pre-write guard, and expert review panels from `claude-plugin`

No API key required. Claude Code is the orchestrator. The harness provides mechanical tools via MCP.

---

## Pipeline

All work follows the same four-stage pipeline. The design stages are skippable for standalone work.

### Full pipeline (feature work with design review)

```
/problem XXXX      → problem.md, requirements.md, solution.md, critic → CHECKPOINT 1
/write-spec XXXX   → reads solution.md → .harness/specs/ (no re-exploration needed)
/build XXXX        → worktree → spec engine → write to target files → diff shown
                   ← review the diff; optionally run /review XXXX
/deliver XXXX      → merge branch → clean up → record learnings
```

### Standalone (isolated unit, no design ceremony)

```
/write-spec <description>   → explore codebase → .harness/specs/<id>.py
/build <spec-id>            → gate engine (temp dir) → artifact
/deliver <run-id>           → write artifact to target file
```

In both paths, gate failures return structured `GateError` objects (`file:line:column:message`). `memory_retrieve` surfaces similar past failures before each repair attempt. In the full pipeline, code is written to an actual worktree and validated against real project context via `gate_run_on_dir`. In standalone mode, code is validated in a temp dir via `gate_run` and only written to disk by `/deliver`.

---

## Setup

```bash
bash /path/to/harness-combined/setup.sh [project-dir]
```

This:
1. Installs slash commands under `.claude/commands/`
2. Registers the MCP server in `.mcp.json`
3. Registers the three hooks in `.claude/settings.json`
4. Copies `CLAUDE.md` to the project root (if not already present)
5. Checks Python tool dependencies

Then open Claude Code in the project and run:

```
/init
```

---

## Gate pipeline

Three hooks enforce quality at write-time and turn-end:

| Hook | Trigger | Scope | Action |
|------|---------|-------|--------|
| `pre_write_guard` | Before Write/Edit | Per file | Blocks forbidden patterns (eval, hardcoded secrets, shell=True, SQL interpolation, etc.) — **before** code is written |
| `post_write_gate` | After Write/Edit | Per file | Runs lint + SAST; returns structured `file:line` findings |
| `stop_full_gate` | After every AI turn | Review-ready worktree | Full suite (lint → type-check → tests → security); blocks turn if failures detected |

All three hooks import from the `gates/` module — one canonical gate implementation, no triplication.

**Gate suites by language** (fail-fast):

| Language | Directory mode (worktree/stop hook) | Text mode (spec/build) |
|---|---|---|
| Python | lint → type_check → tests → security | syntax → type_check → lint → tests → security |
| TypeScript | type_check → lint → tests | type_check → lint → tests |
| Go | build → vet → tests | build → vet → staticcheck → tests |
| Rust | check → clippy → tests | check → clippy → tests → audit |

---

## Failure memory

Gate failures are recorded in `.harness/memory.db` (SQLite + BM25 keyword index). Before every repair attempt, `memory_retrieve` searches for similar past failures by error text. This is cross-session — the model accumulates a project-level library of what went wrong and how it was fixed.

`_learnings.md` (in `.tickets/`) captures higher-level must-fix patterns from critic reviews in human-readable form, trimmed to 200 lines. Both layers are loaded as context at the start of relevant phases.

---

## MCP tools

The harness server exposes these tools to Claude:

| Tool | Workflow | Description |
|------|----------|-------------|
| `gate_run` | Spec/build | Run gates on generated code (text mode, temp dir) |
| `gate_run_on_dir` | Ticket/SDLC | Run gates on actual worktree files (fail-fast) |
| `gate_run_on_dir_full` | Ticket/SDLC | Run all gates on worktree files (no fail-fast, for gate-findings.md) |
| `repair_run` | Spec/build | Apply a unified diff server-side and re-run gates |
| `memory_retrieve` | Both | BM25 search over past gate failures for the same gate |
| `memory_record` | Both | Record a gate failure/resolution for future retrieval |
| `spec_load` | Spec/build | Load a `.harness/specs/<id>.py` as structured JSON |
| `context_fetch` | Spec/build | Read reference files + adjacent directory listing |
| `artifact_save` | Spec/build | Save run artifact (supports custom `artifact_dir`) |
| `artifact_load` | Spec/build | Load a run artifact by run_id |
| `artifact_escalate` | Spec/build | Mark an artifact as escalated |
| `dag_load` | Spec/build | Load and validate a task DAG, return execution layers |
| `checkpoint_read` | Spec/build | Read task resume checkpoint |
| `checkpoint_write` | Spec/build | Write task resume checkpoint |
| `harness_status` | Spec/build | List recent spec/build runs |

---

## Slash commands

### Design phase
| Command | Purpose |
|---|---|
| `/problem` | Start new ticket: clarity check → problem → requirements → solution → critic → checkpoint 1 |
| `/requirements` | Manual requirements phase (escape hatch) |
| `/solution` | Manual solution phase |
| `/refine` | Solution refinement |
| `/score-spec` | Pre-build spec quality gate |

### Build phase
| Command | Purpose |
|---|---|
| `/write-spec XXXX` | Ticket mode: formalize approved solution into specs. Standalone: explore codebase → spec |
| `/build XXXX` | Ticket mode: worktree → spec engine → write target files → diff. Standalone: temp dir → artifact |
| `/deliver XXXX` | Ticket mode: merge + clean up. Standalone: write artifact to target file |
| `/debug` | Classify and explain an escalated standalone build |

### Review & maintenance
| Command | Purpose |
|---|---|
| `/review XXXX` | Structured code review (optional, between `/build` and `/deliver`) |
| `/critique` | Expert panel review of current diff |
| `/gate XXXX` | Manual structured gate run → gate-findings.md |
| `/cancel XXXX` | Abandon ticket: remove worktree, delete branch |
| `/ticket-status` | Open tickets with implementation order |

### Shared
| Command | Purpose |
|---|---|
| `/init` | Initialize the pipeline in the current project |
| `/status` | Combined view: open tickets + recent standalone runs |

---

## System tool requirements

| Language | Required |
|---|---|
| Python | `python`, `mypy`, `ruff`, `bandit`, `pytest` |
| TypeScript | `node`, `npx` (tsc, eslint, jest via npx) |
| Go | `go` (staticcheck optional) |
| Rust | `cargo` (cargo-audit optional) |

Missing tools are skipped gracefully in directory mode; a `TOOL_ERROR` GateError is emitted so the model can diagnose.

---

## Directory structure

```
harness-combined/
├── server.py              ← MCP server (all harness tools)
├── models.py              ← GateError, GateResult, Spec, Task, TaskSpec
├── memory.py              ← SQLiteFailureMemory with BM25 index
├── dag.py                 ← DAGResolver (topological sort + cycle detection)
├── gates/
│   ├── __init__.py        ← run_suite_for (text mode) + run_suite_on_dir (dir mode)
│   ├── python.py          ← Python gates, both modes
│   ├── typescript.py      ← TypeScript gates, both modes
│   ├── go.py              ← Go gates, both modes
│   └── rust.py            ← Rust gates, both modes
├── hooks/
│   ├── pre_write_guard.py ← PreToolUse: block forbidden code patterns
│   ├── post_write_gate.py ← PostToolUse: per-file lint/SAST with structured output
│   ├── stop_full_gate.py  ← Stop: full suite on review-ready worktrees
│   └── hooks.json         ← Hook registration manifest
├── commands/
│   ├── problem.md         ← SDLC entry point
│   ├── write-spec.md      ← Write spec or task DAG
│   ├── build.md           ← Spec/build + worktree workflow
│   ├── deliver.md         ← Merge + worktree cleanup (or write artifact)
│   ├── gate.md            ← Manual gate runner
│   ├── review.md          ← Manual code review
│   ├── critique.md        ← Expert panel review
│   ├── requirements.md    ← Manual requirements phase
│   ├── solution.md        ← Manual solution phase
│   ├── refine.md          ← Solution refinement
│   ├── score-spec.md      ← Spec quality gate
│   ├── cancel.md          ← Cancel ticket
│   ├── ticket-status.md   ← Ticket summary
│   ├── debug.md           ← Debug escalated runs
│   ├── status.md          ← Combined status view
│   └── init.md            ← Initialize both workflows
├── context/
│   ├── critic-brief.md    ← Critic agent shared instructions
│   ├── panels/            ← Expert review panels (Core, Python, HTTP-API, UI, AI-LLM)
│   └── rules/             ← Per-language code generation rules
├── agents/
│   └── critic.md          ← Critic subagent definition
├── CLAUDE.md              ← Working agreement (copy to project root)
├── setup.sh               ← Installation script
└── .claude-plugin/
    └── plugin.json        ← Plugin manifest
```

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
/problem XXXX      → problem.md, requirements.md, solution.md, design critic → CHECKPOINT 1
/write-spec XXXX   → (optional) pre-generate specs from solution.md into .harness/specs/
/build XXXX        → auto-generates specs from solution.md if absent → worktree → spec engine → diff → post-build critic
                   ← review the critic's report; optionally run /review XXXX (interactive)
                     or /critique <files> (free-form comprehensive)
/deliver XXXX      → merge branch → clean up → record learnings
```

### Standalone (isolated unit, no design ceremony)

```
/write-spec <description>      → (optional) pre-generate a spec into .harness/specs/<id>.py
/build <description|spec-id>   → generates a spec from a description if needed → gate engine (temp dir) → artifact
/deliver <run-id>           → write artifact to target file
```

In both paths, gate failures return structured `GateError` objects (`file:line:column:message`). `memory(action="retrieve", ...)` surfaces similar past failures before each repair attempt. In the full pipeline, code is written to an actual worktree and validated against real project context via `gate_run_on_dir`. In standalone mode, code is validated in a temp dir via `gate_run` and only written to disk by `/deliver`.

---

## Setup

Install as a plugin — the manifest at `.claude-plugin/plugin.json` declares the MCP server and hooks, and Claude Code auto-discovers `commands/`, `skills/`, and `agents/`:

```
claude /plugin install /path/to/harness-combined
```

Then open Claude Code in the project and run:

```
/init
```

### Dependencies (auto-bootstrapped)

The MCP server's only third-party dependency is `mcp` (see `requirements.txt`). You do **not** need to install it yourself. The server is launched via `bin/harness-server`, which on first run creates a plugin-local virtualenv at `.venv/` and installs the requirements into it, then execs `server.py` with that interpreter. This keeps the harness working even when the system `python3` is externally managed (PEP 668), and avoids polluting global site-packages. The first launch takes ~30s while the venv builds; subsequent launches are instant.

- The venv is git-ignored and self-heals (it rebuilds if deleted or if `mcp` stops importing).
- Bootstrapping uses `python3` from `PATH`. To pin a different interpreter, set `HARNESS_PYTHON=/path/to/python3` in the MCP server's environment.
- The Write/Edit/Stop hooks run on bare `python3` — they import only the standard library and the plugin's own modules, so they need no venv.

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

## Memory contract

Two layers, no overlap:

| Layer | Audience | Written by | Read by |
|---|---|---|---|
| `.harness/memory.db` | machine only (opaque) | `memory(action="record", ...)` after each gate cycle | `memory(action="retrieve", ...)` before each repair attempt |
| `.tickets/_learnings.md` | lead-curated | `/deliver` and `/harvest-learnings` (append-only, after lead approval) | loaded as context at `/problem` and `/build` |
| `.tickets/_standards.md` | lead only | the lead, by hand | loaded as context at `/problem` and `/build` |

The machine maintains its own BM25-searchable failure trail in `memory.db` and consults it during repair. `_standards.md` is hand-edited by the lead only. `_learnings.md` (must-fix patterns) is appended to by `/deliver` and `/harvest-learnings` — but only entries the lead accepts, via a template-field-only write path that never overwrites existing content or writes raw extracted text. `/harvest-learnings` reads the auto-populated `memory.db` for recurring cross-ticket patterns and is the always-available capture path; `/deliver`'s capture is opportunistic — it fires only when the ticket has a `gate-findings.md` (e.g. from a manual `/gate` run).

`/init` creates `_standards.md` and `_learnings.md` as stubs so the harness finds the files it expects from the first session. Edit the standards file before your first `/problem`.

---

## MCP tools

The harness server exposes these tools to Claude:

| Tool | Workflow | Description |
|------|----------|-------------|
| `gate_run` | Spec/build | Run gates on generated code (text mode, temp dir) |
| `gate_run_on_dir` | Ticket/SDLC | Run gates on a worktree; `fail_fast=True` (default) for repair loop, `fail_fast=False` for gate-findings.md |
| `repair_run` | Spec/build | Apply a unified diff server-side and re-run gates |
| `memory` | Both | `action="record"` saves a failure/resolution; `action="retrieve"` BM25-searches past failures |
| `spec_load` | Spec/build | Load a `.harness/specs/<id>.py` as structured JSON |
| `context_fetch` | Spec/build | Read reference files + adjacent directory listing |
| `artifact` | Spec/build | `action="save"` persists a run; `action="load"` reads by run_id; `action="escalate"` marks exhausted |
| `dag_load` | Spec/build | Load and validate a task DAG, return execution layers |
| `checkpoint` | Spec/build | `action="read"` returns completed spec IDs; `action="write"` saves progress |
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

### Build phase
| Command | Purpose |
|---|---|
| `/write-spec <arg>` | **Optional** spec-authoring step. Routes to ticket flow (digit-prefixed arg) or spec flow (free-form description). `/build` self-specs when specs are absent, so this is only needed to pre-generate or hand-tune a spec. |
| `/build <arg>` | Single entry point for implementation. Generates specs first if none exist for the ticket/description, then routes to ticket flow (worktree + diff) or spec flow (temp dir + artifact). |
| `/deliver <arg>` | Single entry point for shipping. Routes to ticket flow (merge + cleanup) or spec flow (write artifact to target). |

Each of these three commands is a **thin controller** in `commands/`. It inspects the argument, decides which mode applies, and reads the corresponding flow file from `context/flows/<command>-<mode>.md`. Only one flow file is loaded per invocation — keeps context lean and keeps the user-facing surface to one command per concept.

### Maintenance
| Command | Purpose |
|---|---|
| `/gate XXXX` | Manual structured gate run → `gate-findings.md` |
| `/bisect --good <ticket-or-ref> [--bad <ticket-or-ref>] [--run <cmd>]` | Ticket-aware `git bisect`: finds the regression commit and names the ticket that introduced it. Output uses a UTF-8 em-dash: `Regression introduced in commit <sha> — part of ticket XXXX (<title>)`. |
| `/cancel XXXX` | Abandon ticket: remove worktree, delete branch |
| `/ticket-status` | Open tickets with implementation order |
| `/export [--format json\|csv] [--all] [--output <file>]` | Export ticket data (number, title, status, summaries, commits) from `.tickets/` to JSON or CSV. Completed tickets by default; `--all` for every status. |
| `/velocity` | Cycle-time report over completed tickets: per-ticket detail table, weekly ISO-week summary, and overall average. Date math is delegated to `skills/velocity/compute.py` (deterministic; ticket data piped via stdin). |
| `/sprint [--sprint-capacity N] [--max-sprints N] [--as-of YYYY-MM-DD]` | Group open tickets into a dependency-ordered, capacity-bounded weekly sprint plan with a backlog-overflow section. Topological sort, bin-packing, and date labeling are delegated to `skills/sprint/compute.py` (deterministic; ticket data piped via stdin). Read-only. |
| `/init` | Initialize the pipeline in the current project |

---

## Skills (intent-triggered)

These seven behaviors are skills rather than commands. Invoke them explicitly with `/<name>` or just describe the intent — the model will pick the right skill from the description.

| Skill | Triggers on | Purpose |
|---|---|---|
| `suggest` | "what should we build next?", "what features are missing?", "suggest something" | Inventories current capabilities and open tickets, compares against comparable tools, surfaces up to 10 non-duplicate improvement ideas, emits `/problem`-ready lines for accepted suggestions. |
| `usage-report` | "review my Claude Code usage", "where am I spending tokens/time", "how can I use Claude more efficiently" | Runs a deterministic analyzer over local `~/.claude` state and writes a dated report: usage patterns, an idle-excluded time estimate, strengths/weaknesses, and roadmap-tied recommendations. |
| `review` | "review ticket 0003", "is 0007 ready to merge?" | Ticket-scoped post-build review against problem / requirements / solution. Sets `changes-requested` if must-fix found. |
| `critique` | "critique my changes", "expert panel review of the auth route" | Free-form expert-panel critique of the current diff or specified files. Writes `CRITIQUE.md`. |
| `requirements-review` | "review requirements", "is 0034 ready to build?", "/requirements-review 0034" | Pre-build checkpoint: reviews `requirements.md` against `problem.md` across completeness, testability, coverage, consistency in a scoped read-only subagent; writes advisory `requirements-findings.md`. |
| `status` | "what's open?", "where are we?" | Combined view of tickets + standalone runs + failure-memory presence. |
| `debug` | "why did the build escalate?", "the run gave up — what now?" | Classify and explain an escalated standalone run; propose targeted fix. |

**Two review cycles run automatically:**

- **Pre-build (design)** — `/problem` Phase 5 spawns the critic subagent against `problem.md` / `requirements.md` / `solution.md`. Findings revise `solution.md` before Checkpoint 1. Max 2 rounds.
- **Post-build (code)** — `/build` Step 7 spawns the critic subagent against the worktree, with `problem.md` / `requirements.md` / `solution.md` as the ticket baseline. BLOCKER and MAJOR findings are must-fix: `/build` auto-repairs them and re-spawns the critic to verify, looping up to `MAX_REPAIR_ATTEMPTS` (default 3); only on exhaustion does it set `changes-requested` and ask the lead. MINOR / OBS are optional — listed, never auto-fixed.

Two **optional** manual follow-ups are available between `/build` and `/deliver`:

- `/review XXXX` — same panel-aware review as the post-build critic, but **interactive**: findings stream in the conversation, lead can ask follow-up questions, request deeper dives, or skip ahead to verdict. Use when you want to walk the review conversationally rather than read a one-shot report.
- `/critique <files>` — comprehensive on-demand panel critique against arbitrary files. Works on code (`/critique src/auth/`) or design artifacts (`/critique problem.md solution.md`). Free-form scope; not tied to a ticket; output written to `CRITIQUE.md`.

---

## Expert review panels

The `critique` skill loads domain-specialist panels based on the files in scope. Each panel names 1–3 working experts, captures their key positions, and lists hazards with severity. Panels are additive — a Python route handler returning an HTMX swap activates Core + Python + HTTP/API + Hypermedia + UI simultaneously, each contributing findings from its own lens.

| Category | Panel | Panelists | Trigger |
|---|---|---|---|
| **Foundation** | `core` | Martin, Parnas, Ousterhout, Fowler, Beck, McGraw, Evans, Wright (Hyrum's Law) | Always active |
| **Languages** | `python` | Hettinger, Beazley | `.py` files, Python project markers |
| | `typescript` | Hejlsberg, Collina | `.ts` / `.tsx` / `.js`, `package.json` |
| | `go` | Pike, Kennedy | `.go`, `go.mod` |
| | `rust` | Matsakis, Gjengset | `.rs`, `Cargo.toml` |
| | `jvm` | Goetz, Bloch | `.java` / `.kt`, Gradle / Maven |
| | `cpp` | Stroustrup, Sutter | `.c` / `.cpp` / `.h`, `CMakeLists.txt` |
| | `shell` | Wooledge, Ramey | `.sh` / `.bash`, shell shebangs |
| **Frontend frameworks** | `angular` | Gechev, Lesh | `@angular/core`, `angular.json` |
| | `react` | Abramov, Linsley | `react` package, React JSX/TSX |
| | `vue` | Evan You, Anthony Fu | `vue` package, `.vue` files |
| | `svelte` | Rich Harris | `svelte` / `@sveltejs/kit`, `.svelte` files |
| | `solid` | Ryan Carniato | `solid-js` / `@solidjs/start` |
| **HTTP / Web** | `http-api` | Fielding, Nottingham, Sturgeon | Route handlers, OpenAPI specs |
| | `hypermedia` | Gross, Nottingham | HTMX detected (deps or markup) |
| | `ui` | Keith, Pickering, Wathan, Frost | HTML / CSS / JSX, inline markup |
| | `uswds` | Frost (lens applied to USWDS) | `@uswds/uswds`, `usa-*` classes |
| **Security** | `identity` | Parecki, Richer | OAuth / OIDC / JWT / session libs |
| | `cryptography` | Valsorda, Green | Crypto / password-hash / TLS code |
| **Data** | `database` | Kleppmann, Winand | Migrations, ORM, raw SQL |
| | `data-engineering` | Beauchemin, Handy, Sculley | Airflow / dbt / Spark / ML pipelines |
| **AI** | `ai-llm` | Willison, Husain, Yan | LLM clients, RAG, embeddings, evals |
| **Operations** | `cicd` | Humble & Farley, Rice | `.github/workflows/`, Dockerfile, lockfiles |
| | `infrastructure` | Morris, Hightower | Terraform, K8s manifests, Helm |
| | `observability` | Majors, Sridharan | Telemetry, logging, traces |
| | `performance` | Gregg, Thompson | Hot-path code, benchmarks |
| | `testing` | Dodds, Feathers | Test suites and runner configs |
| | `distributed` | Newman, Richardson | Queues, RPC, webhooks, sagas |
| **Fallback** | `secondary` | Ramalho, Soueidan | Loaded on demand when primary panels reach an impasse |

Panel files live in `context/panels/<name>.md`. The full trigger conditions, hazard tables, and synthesis rules are in `skills/critique/SKILL.md`. When more than five panels activate on a single review, findings are prioritized by severity across all panels rather than enumerated per panel.

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
│   └── stop_full_gate.py  ← Stop: full suite on review-ready worktrees
├── commands/
│   ├── problem.md         ← SDLC entry point
│   ├── write-spec.md      ← Write spec or task DAG
│   ├── build.md           ← Spec/build + worktree workflow
│   ├── deliver.md         ← Merge + worktree cleanup (or write artifact)
│   ├── gate.md            ← Manual gate runner
│   ├── requirements.md    ← Manual requirements phase
│   ├── solution.md        ← Manual solution phase
│   ├── refine.md          ← Solution refinement
│   ├── cancel.md          ← Cancel ticket
│   ├── ticket-status.md   ← Ticket summary
│   ├── init.md            ← Initialize both workflows
│   └── usage-report.md    ← Analyze own Claude Code usage
├── skills/
│   ├── suggest/SKILL.md   ← Feature suggestion skill (eval-fixture.md for testing)
│   ├── review/SKILL.md    ← Ticket-scoped post-build review
│   ├── critique/SKILL.md  ← Expert-panel critique of a diff
│   ├── status/SKILL.md    ← Combined tickets + spec/build view
│   ├── debug/SKILL.md     ← Postmortem for escalated runs
│   └── usage-report/      ← Usage analysis (SKILL.md + analyze.py)
├── context/
│   ├── critic-brief.md    ← Critic agent shared instructions
│   ├── flows/             ← Mode-specific procedures loaded by /build, /write-spec, /deliver
│   ├── panels/            ← 29 expert review panels — see "Expert review panels" section below
│   └── rules/             ← Per-language code generation rules
├── agents/
│   └── critic.md          ← Critic subagent definition
├── CLAUDE.md              ← Working agreement (copy to project root)
└── .claude-plugin/
    └── plugin.json        ← Plugin manifest
```

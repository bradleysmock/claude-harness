# harness-combined: System Design

This is the entry point for a four-part design series describing `harness-combined`, a Claude Code plugin that turns Claude into a governed SDLC pipeline: design review, TDD-enforced implementation, multi-language quality gates, and git-coordinated multi-developer delivery — with no API key of its own and no network dependency beyond `git`/`gh`.

Read this document first for the shape of the whole system and how a normal session actually flows. The other three go deep on one layer each:

1. **00-overview.md** (this document) — architecture, philosophy, the ticket lifecycle, normal usage
2. **[01-gates-and-hooks.md](01-gates-and-hooks.md)** — the mechanical quality-enforcement layer: hooks, gate suites, SAST, policy, anti-cheat
3. **[02-commands-and-skills.md](02-commands-and-skills.md)** — the full command/skill/agent catalog and the SDLC flows they drive
4. **[03-mcp-server.md](03-mcp-server.md)** — the MCP server: every tool, the data models, memory, and the supporting Python modules
5. **[04-human-in-the-loop.md](04-human-in-the-loop.md)** — where the lead fits, how the harness escalates back to a human, and how to dial autonomy up or down

For line-level operational detail (exact config syntax, status-transition tables, artifact size limits) the canonical reference remains `harness-combined/context/harness-reference.md`, loaded on demand by the flows themselves. This series is the map; that file is the territory for anyone editing the harness itself.

---

## What problem this solves

Claude Code is capable of end-to-end feature delivery, but left alone it will happily generate code that isn't tested, skip design review under time pressure, silently weaken a test to make a gate pass, or lose track of what's been reviewed across a long repair loop. `harness-combined` doesn't ask Claude to be more disciplined — it wraps the model in mechanical checkpoints that don't rely on the model remembering to be careful.

The plugin combines two systems that used to be separate:

- A **structured execution engine**: a polyglot gate pipeline (lint → type-check → tests → security), a diff-based repair loop, and a BM25-searchable failure memory. This part doesn't know what a "ticket" is — it just runs gates on code and reports structured failures.
- An **SDLC workflow**: a two-checkpoint feature pipeline (problem → design → TDD → critic review → merge), a preventive pre-write guard, and expert review panels. This part owns the ticket lifecycle and orchestrates the execution engine underneath it.

Both share the same gate engine and failure memory, so a solo standalone fix and a fully-reviewed ticket get the identical quality bar — the difference is ceremony, not rigor.

---

## Design philosophy

**Deterministic authority lives in Python; judgment lives in the model.** This is the single rule that explains most of the architecture. Anything two independent runs must agree on — a gate verdict, a line-count limit, a dependency cycle, a commit format — is computed by a Python function and returned as a fact. The model never overrides a computed verdict; if it disagrees, it flags a suspected tool defect to the lead, but the verdict stands until the Python side changes. Judgment — design tradeoffs, critique, repair strategy, remediation wording — stays with the model, because that's the one thing Python can't do.

This shows up everywhere:

- Gates return structured `GateError` objects, never a doctored PASS. When a required tool is missing, the gate reports `TOOL_ERROR`/skipped — the model never substitutes its own guess for a check it couldn't run.
- The critic and craft subagents are **read-only-reasoning**: they emit structured findings/JSON, and a separate mechanical step (gate re-run, pinned-test survival, `finding_key` reconciliation) decides whether a proposed change is safe — the agent's own claim of "this is behavior-preserving" is never trusted on its own.
- `repair_integrity.py` classifies a repair diff for test-weakening or bare-suppression patterns mechanically, closing the obvious way a model under pressure would otherwise "fix" a failing gate by disabling the thing that caught it.
- Ticket numbering, delivery, and dependency-cycle detection are git-coordinated append-only ledger operations, not something either the model or a human keeps straight in their head.

**No API key, no daemon.** Claude Code is the only orchestrator — the MCP server is a mechanical tool layer (gate running, memory, spec loading), not a second agent loop. Everything is a subprocess call or a SQLite/filesystem read. The one exception, `autopilot-watch`, is an opt-in local background process with no model calls of its own — it just dispatches `/autopilot` at the right moment.

**Fail-closed by default, fail-open only where a false block would be worse than a false pass.** Most gates and guards fail closed: an unparseable coverage report is `passed=False`, not "skip and hope." A few specific things fail open deliberately, and always for a stated reason — audit logging (`audit.py`) never blocks the real operation over a logging failure, and `dep_audit_enabled()` stays enabled on a broken config because silently disabling a security gate is the worse failure mode. The rule is: fail closed unless failing closed would itself create a bigger, quieter risk.

---

## Two workflow modes, one engine

| | **Ticket / SDLC mode** | **Standalone / spec mode** |
|---|---|---|
| Entry point | `/problem XXXX` | `/write-spec <description>` (optional) or straight to `/build <description>` |
| Ceremony | Design docs, checkpoint approval, critic review, craft polish | None — one spec, one build, one artifact |
| Where code lives during build | A real worktree (`.worktrees/XXXX-<slug>`) validated with full project context | A temp directory, validated in isolation |
| Gate entry point | `gate_run_on_dir` | `gate_run` |
| Delivery | `/deliver XXXX` — squash-merges the branch into `main` | `/deliver <run-id>` — writes the artifact to its target file |
| Use when | The change needs a defined user, an approved design, and a durable ticket record | The unit is isolated and self-evident — a script, a small fix, a generated snippet |

Both paths return the same structured `GateError` shape and consult the same failure memory before each repair attempt. The difference is entirely about how much ceremony the work needs, never about how rigorously it's checked.

---

## The ticket lifecycle, in brief

Full detail (state table, ledger transaction semantics, squash-delivery mechanics) is in `context/harness-reference.md` and in [02-commands-and-skills.md](02-commands-and-skills.md). The shape every engineer needs up front:

- **`main` carries almost nothing about in-flight work.** A ticket's design docs, implementation, and every intermediate status live on its feature branch (`ticket/XXXX-<slug>`), in its own worktree (`.worktrees/XXXX-<slug>`). `main` receives exactly **one commit per delivered ticket** — a squash merge at `/deliver` that folds the `→ done` transition and the doc archive into a single commit.
- **Numbering and coarse lifecycle events are git-coordinated**, not filesystem-coordinated. An orphan branch, `harness-tickets`, holds an append-only `ledger.jsonl`: `claim` / `delivered` / `cancelled` / `abandoned` / `reopened` events, pushed first-wins. This is what makes it safe for two developers to run `/problem` at the same time without colliding on a ticket number.
- **Fine-grained status** (`solution`, `implementing`, `review-ready`, `changes-requested`) lives only in the worktree's copy of `status.md`, never on `main`. Every resolver in the codebase follows one rule: if a worktree exists, its `status.md` is authoritative; otherwise fall back to the ledger's coarse state or `main`'s `completed/` archive.
- **Approval is a specific, checkable fact, not a vibe.** When the lead approves at Checkpoint 1, `/problem` stamps `approved-commit` (a SHA). `autopilot-watch` and `/autopilot` both re-verify, before building, that the design files are byte-identical between that SHA and the branch's current HEAD — any later edit to the design without a fresh approval is treated as unapproved, never built.

---

## Normal usage: full pipeline

```
/problem XXXX      → problem.md, requirements.md, solution.md, design critic → CHECKPOINT 1 (lead approves)
/build XXXX        → auto-generates specs if absent → worktree → red-gate check → TDD implementation
                    → gate/repair loop → post-build critic (auto-repairs BLOCKER/MAJOR) → craft polish pass
/review XXXX        (optional) interactive re-review, or /critique <files> for a free-form panel pass
/deliver XXXX      → squash-merge → cleanup → learnings capture
```

A concrete walk-through:

1. **`/problem XXXX`** — the lead describes the work. A clarity check asks only if the user, the outcome, or the scope is genuinely missing; otherwise it proceeds. It claims a ticket number off the ledger, creates the branch and worktree, and writes `problem.md` → `requirements.md` → `solution.md` in sequence, each capped to a hard line limit (40/60/80 lines) to keep the docs skimmable. A design-phase critic pass runs against all three artifacts (max 2 rounds) before the lead sees **Checkpoint 1** — a concise "what was decided, what the critic found, what changed" summary, not a blow-by-blow narration.
2. **`/build XXXX`** — resumes the existing worktree. If no specs exist yet, it generates them from `solution.md` inline (`/write-spec` beforehand is optional, for pre-generating or hand-tuning). For each spec, a **red-gate check** runs the newly-written test in isolation and confirms it actually fails before any implementation is written — TDD enforced mechanically, not by instruction. Implementation proceeds under the gate/repair loop (lint → type-check → tests → security, `MAX_REPAIR_ATTEMPTS` retries, failure memory consulted both before generation and after each failure). Once gates are green, the post-build critic runs against the full worktree with the ticket's problem/requirements/solution as baseline; BLOCKER and MAJOR findings trigger an auto-repair loop with re-verification, and only exhaustion escalates to the lead as `changes-requested`. After functional acceptance, a **craft polish pass** proposes bounded, behavior-preserving naming/structure/restraint improvements, each round gated by a full re-run plus pinned-test survival before it's kept.
3. **Optional manual review** — `/review XXXX` walks the same panel-aware review conversationally; `/critique <files>` runs a free-form expert-panel pass over arbitrary scope, ticket or not.
4. **`/deliver XXXX`** — preflight checks (commit-message lint, coverage enforcement, a rebase-against-`main` guard, a refine-touched confirmation if the design was machine-adjusted mid-build), then a `git merge --squash` onto `main`, ticket archive, ledger `delivered` event, worktree/branch cleanup, and — if the ticket produced `gate-findings.md` or `critic-findings.md` — an opportunistic learnings capture into the lead-curated `_learnings.md`.

**Autopilot** (`/autopilot XXXX`) runs this same pipeline unattended once a ticket is approved, pausing only for a genuine block (spec-remediation exhausted, repair loop exhausted) or a scope-drift confirmation. `/autopilot-watch` is a standalone background loop that dispatches it automatically — see [02-commands-and-skills.md](02-commands-and-skills.md) for the autopilot family in full, including batch mode.

## Normal usage: standalone

```
/write-spec <description>      (optional) pre-generate a spec
/build <description|spec-id>   → generates a spec if needed → gate engine (temp dir) → artifact
/deliver <run-id>               → write artifact to target file
```

No worktree, no critic, no checkpoint — the gate engine and failure memory are the only ceremony, run against a temp directory via `gate_run` instead of `gate_run_on_dir`. Use this for isolated, self-evident units; reach for `/problem` when the work needs a defined user, an approved design, or a durable record.

---

## Directory map

```
harness-combined/
├── server.py, models.py, memory.py, dag.py     ← MCP server core (see 03-mcp-server.md)
├── ticket.py, ticket_deps.py, ticket_templates.py  ← ticket state machine, dependency graph, templates
├── audit.py, health.py, flaky_detect.py, learnings.py, panel_detect.py,
│   context_rank.py, dry_run.py, sarif_output.py, spec_coverage.py, mode_branch.py
│                                                ← supporting Python modules (see 03-mcp-server.md)
├── gates/                                       ← every gate implementation (see 01-gates-and-hooks.md)
├── hooks/                                       ← the five registered hooks (see 01-gates-and-hooks.md)
├── commands/                                    ← 30 slash commands (see 02-commands-and-skills.md)
├── skills/                                      ← intent-triggered skills (see 02-commands-and-skills.md)
├── agents/                                      ← critic, craft, requirements-analyst subagent defs
├── context/
│   ├── harness-reference.md                     ← exhaustive operational reference
│   ├── critic-brief.md, score-spec.md, spec-remediation.md
│   ├── flows/                                   ← mode-specific step-by-step procedures
│   ├── panels/                                  ← expert review panel definitions + triggers.md
│   ├── helpers/, rules/
├── validators/                                   ← standards_validator.py, score_spec.py
├── bin/                                          ← harness-server, autopilot-watch, bisect-resolve.sh
├── CLAUDE.md                                     ← working agreement (copy to project root)
└── .claude-plugin/plugin.json                    ← plugin manifest: MCP server + hook registration
```

## Where to go next

- Enforcing quality mechanically (hooks, gate suites, SAST, policy, anti-cheat): **[01-gates-and-hooks.md](01-gates-and-hooks.md)**
- The full command/skill/agent catalog and how they drive the pipeline above: **[02-commands-and-skills.md](02-commands-and-skills.md)**
- The MCP server's tools, data models, and memory/DAG subsystems: **[03-mcp-server.md](03-mcp-server.md)**
- Where the lead fits, escalation triggers, and autonomy controls: **[04-human-in-the-loop.md](04-human-in-the-loop.md)**

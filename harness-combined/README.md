# harness-combined

A unified Claude Code harness that combines two complementary systems:

- **Structured execution engine** — polyglot gate pipeline (lint → type-check → tests → security), diff-based repair loop, and BM25 failure memory from `harness-no-api-key`
- **SDLC workflow** — two-checkpoint feature pipeline (problem → design → TDD → critic review → merge), preventive pre-write guard, and expert review panels from `claude-plugin`

No API key required. Claude Code is the orchestrator. The harness provides mechanical tools via MCP.

---

## Documentation

This README is a quick start. The full design is a five-part series in [`docs/design/`](docs/design/):

- **[00-overview.md](docs/design/00-overview.md)** — architecture, design philosophy, the ticket lifecycle, and normal usage end to end
- **[01-gates-and-hooks.md](docs/design/01-gates-and-hooks.md)** — every hook, every gate, SAST, policy, and the anti-cheat machinery
- **[02-commands-and-skills.md](docs/design/02-commands-and-skills.md)** — the full command/skill/agent catalog and expert review panels
- **[03-mcp-server.md](docs/design/03-mcp-server.md)** — every MCP tool, the data models, memory, and DAG subsystems
- **[04-human-in-the-loop.md](docs/design/04-human-in-the-loop.md)** — where the lead fits, how the harness escalates back to a human, and how to dial autonomy up or down

For line-level operational detail (exact config syntax, status-transition tables, artifact size limits) see `context/harness-reference.md`, which the flows themselves load on demand.

---

## Pipeline

All work follows the same four-stage pipeline. The design stages are skippable for standalone work.

### Full pipeline (feature work with design review)

```
/problem XXXX      → problem.md, requirements.md, solution.md, design critic → CHECKPOINT 1
/build XXXX        → auto-generates specs if absent → worktree → TDD implementation
                   → gate/repair loop → post-build critic → craft polish
                   ← review the critic's report; optionally run /review XXXX (interactive)
                     or /critique <files> (free-form comprehensive)
/deliver XXXX      → merge branch → clean up → record learnings
```

### Standalone (isolated unit, no design ceremony)

```
/write-spec <description>      → (optional) pre-generate a spec into .harness/specs/<id>.py
/build <description|spec-id>   → generates a spec from a description if needed → gate engine (temp dir) → artifact
/deliver <run-id>               → write artifact to target file
```

In both paths, gate failures return structured `GateError` objects (`file:line:column:message`). `memory(action="retrieve", ...)` surfaces similar past failures before each repair attempt. In the full pipeline, code is written to an actual worktree and validated against real project context via `gate_run_on_dir`. In standalone mode, code is validated in a temp dir via `gate_run` and only written to disk by `/deliver`.

See [00-overview.md](docs/design/00-overview.md) for the full walkthrough, the autopilot family, and how ticket state, the delivery ledger, and multi-developer coordination fit together.

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

## Gates, hooks, and memory

Five hooks enforce quality at write-time and turn-end, and a shared gate engine runs the same lint → type-check → tests → security suite (Python/TypeScript/Go/Rust, both directory and text mode) whether the change is a ticket or a standalone spec. Full detail — including baseline-delta test regression tolerance, the SAST/secrets/coverage/dep-audit gates, the parallel scheduler, the data-driven promotion policy, and pluggable SARIF-in external gates — is in **[01-gates-and-hooks.md](docs/design/01-gates-and-hooks.md)**.

Failure memory is a two-layer contract: an opaque, BM25-searchable `.harness/memory.db` consulted both reactively (during repair) and proactively (before generation), plus a lead-curated `_learnings.md`/`_standards.md` pair that the machine never writes to directly. `/init` creates the lead-curated files as stubs — edit `_standards.md` before your first `/problem`.

---

## System tool requirements

| Language | Required |
|---|---|
| Python | `python`, `mypy`, `ruff`, `bandit`, `pytest` |
| TypeScript | `node`, `npx` (tsc, eslint, jest via npx) |
| Go | `go` (staticcheck optional) |
| Rust | `cargo` (cargo-audit optional) |

Missing tools are skipped gracefully in directory mode; a `TOOL_ERROR` GateError is emitted so the model can diagnose. Run `/doctor` for a read-only report of what's missing.

---

## Directory structure

See [00-overview.md](docs/design/00-overview.md#directory-map) for the current, complete directory map with pointers to where each piece is documented.

`CLAUDE.md` (the working agreement, copied to the project root by `/init`) and `.claude-plugin/plugin.json` (the plugin manifest — MCP server registration and hook wiring) are the two files worth reading directly rather than through the docs series.

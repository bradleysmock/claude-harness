# Harness Reference

Operational details for the harness-combined pipeline. Loaded on demand — not in every session context.

---

## Tickets

All SDLC work is tracked under `.tickets/`.

```
.tickets/
  NEXT_TICKET        # Next available ticket number (atomic counter)
  .ticket.lock       # Lock file — present only during number claim (format: pid:epoch)
  .active            # Active session ticket slug (scopes stop hook)
  _standards.md      # Lead-curated engineering standards (created by /init)
  _learnings.md      # Lead-curated must-fix patterns (created by /init)
  XXXX-<slug>/
    problem.md
    requirements.md
    solution.md
    status.md
    gate-findings.md
```

Numbers are four-digit zero-padded (`0001`, `0002`, ...). `status.md` format:
```
status: <stage>
ticket: XXXX
title: <short human-readable title>
branch: ticket/XXXX-<slug>
updated: YYYY-MM-DD
```

### Status transitions

| Status              | Set by                          | Transitions to                        |
|---------------------|---------------------------------|---------------------------------------|
| `problem`           | `/problem` Phase 2              | `requirements`                        |
| `requirements`      | `/problem` Phase 3              | `solution`                            |
| `solution`          | `/problem` Phase 4              | `implementing`                        |
| `implementing`      | `/build` setup                  | `review-ready`                        |
| `review-ready`      | `/build` after gate/repair loop | `done` or `implementing`              |
| `changes-requested` | `review` skill                  | `implementing` (re-run `/build`)      |
| `done`              | `/deliver`                      | — (terminal)                          |
| `cancelled`         | `/cancel`                       | — (terminal)                          |

> **Self-speccing:** `/write-spec` never changed `status`; the `solution → implementing` transition has always been driven by `/build` setup. As of the merged build flow, `/build` also *generates* the spec/task files inline when it starts from `status: solution` with no specs present. `/write-spec` is therefore an optional pre-step, not a required transition.

---

## Worktrees

- **Branch naming**: `ticket/XXXX-<slug>`
- **Worktree location**: `.worktrees/XXXX-<slug>` — globally git-ignored
- All implementation happens in the worktree. **Never commit implementation to main directly.**
- The worktree is merged to main only after the lead approves the post-build diff.

---

## Gate Pipeline

Three hooks enforce quality at write-time and turn-end:

| Hook              | Trigger                       | Scope                        | What it checks |
|-------------------|-------------------------------|------------------------------|----------------|
| `pre_write_guard` | Before every Write/Edit       | Per file                     | Forbidden code shapes: eval, hardcoded secrets, `shell=True`, SQL interpolation. **Blocks the write.** |
| `post_write_gate` | After every Write/Edit        | Per file                     | Lint + SAST (ruff/bandit, eslint, gofmt, rustfmt). Structured `file:line` output. |
| `stop_full_gate`  | Stop event (turn end)         | Worktree (review-ready only) | Full suite: lint → type-check → tests → security. Blocks the turn. |

### Gate suites by language (fail-fast — first failure stops the run)

| Language   | Directory mode (worktree)             | Text mode (spec/build)                            |
|------------|---------------------------------------|---------------------------------------------------|
| Python     | lint → type_check → tests → security  | syntax → type_check → lint → tests → security     |
| TypeScript | type_check → lint → tests             | type_check → lint → tests                         |
| Go         | build → vet → tests                   | build → vet → staticcheck → tests                 |
| Rust       | check → clippy → tests                | check → clippy → tests → audit                    |

---

## Gate/Repair Loop

When a gate fails in `/build`:

1. Note `gate` name and `errors` array (each with `file`, `line`, `column`, `code`, `message`).
2. Call `memory(action="retrieve", ...)` — similar past failures often reveal the root cause.
3. Fix the specific `file:line` locations using the structured error data.
4. Re-run the gate. Repeat up to `MAX_REPAIR_ATTEMPTS` (default 3).
5. On success, call `memory(action="record", ...)` to store the fix for future sessions.

In spec/build (standalone) mode, `repair_run` applies a unified diff server-side — only the diff and results travel through context.

---

## Memory Contract

Two independent memory layers, no overlap:

| Layer | Audience | Written by | Read by | Purpose |
|---|---|---|---|---|
| `.harness/memory.db` | Machine only (opaque) | `memory(action="record", ...)` after each gate cycle | `memory(action="retrieve", ...)` before each repair attempt | BM25-searchable failure trail. |
| `.tickets/_learnings.md` | Lead only | The lead, by hand | Loaded at `/problem` and `/build` | Human-curated must-fix patterns. |
| `.tickets/_standards.md` | Lead only | The lead, by hand | Loaded at `/problem` and `/build` | Project engineering standards. |

`/deliver` may **suggest** candidate learnings but never writes to `_learnings.md`. `/init` creates both files as stubs.

---

## Artifact Constraints

| Artifact          | Hard limit |
|-------------------|------------|
| `problem.md`      | 40 lines   |
| `requirements.md` | 60 lines   |
| `solution.md`     | 80 lines   |

Use bullet points, not prose. Omit sections that don't apply.

---

## Multi-Agent Critique

The critic subagent (`critic`) is read-only. It loads expert panels by file scope and produces structured BLOCKER / MAJOR / MINOR / OBS findings with `file:line` references — the same 4-tier vocabulary the `critique` and `review` skills use, ensuring one severity model across every review path in the harness.

The critic runs **automatically at both SDLC checkpoints**:

- **Pre-build / design phase**: `/problem` Phase 5 spawns the critic with `Phase: design` against the three design artifacts. Max 2 rounds. Findings revise `solution.md` before Checkpoint 1.
- **Post-build / code phase**: `/build` Step 7 spawns the critic with `Phase: code` against the worktree, using `problem.md` / `requirements.md` / `solution.md` as the ticket baseline. BLOCKER **and** MAJOR findings are must-fix: `/build` auto-repairs them in the worktree and re-spawns the critic to verify, looping up to `MAX_REPAIR_ATTEMPTS` (default 3) before consulting the lead. Only if auto-repair is exhausted does it set `status: changes-requested` and ask for the lead's input. MINOR / OBS findings are never auto-fixed — they are listed for the lead. The manual `/review` skill is the conversational re-review path.

Optional manual review paths after the post-build critic:

- `/review XXXX` — same panel-aware machinery as the critic's `Phase: code` mode, but **interactive** (findings stream in the conversation, lead can ask follow-up questions). Use to re-review after fixing BLOCKERs, drive the review conversationally, or review a ticket whose `/build` happened in a previous session.
- `/critique <files>` — comprehensive on-demand panel critique against arbitrary files, code or design artifacts. Free-form scope; not tied to a ticket.

Severity tiers (canonical — used by `critique`, `review`, and the critic subagent):

- **BLOCKER** — serious design problem likely to cause bugs, maintenance failure, or security issues. Blocks merge. Resolved before `/deliver`.
- **MAJOR** — clear violation of a principle with meaningful consequences. Fix now, or open a new ticket if the effort is large.
- **MINOR** — improvement opportunity. Fix if the code is being touched anyway; otherwise logged.
- **OBS** — observation worth noting. May reflect a legitimate tradeoff. Logged in the deliver summary only.

Must-fix vs. optional differs by review path:

- **`/build` post-build critic** — BLOCKER **and** MAJOR are must-fix and trigger the auto-repair loop (Step 7a); `changes-requested` fires only when that loop is exhausted. MINOR / OBS are optional — listed for the lead, never auto-fixed.
- **`review` skill (interactive)** — `changes-requested` fires on BLOCKER findings; MAJOR / MINOR / OBS appear in the report for the lead to decide on.

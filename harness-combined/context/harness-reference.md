# Harness Reference

Operational details for the harness-combined pipeline. Loaded on demand — not in every session context.

---

## Tickets

All SDLC work is tracked under `.tickets/`.

```
.tickets/
  .ticket.lock       # Lock file — present only during a same-machine number claim (format: pid:epoch)
  .active            # Active session ticket slug (scopes stop hook)
  _standards.md
  _learnings.md
  XXXX-<slug>/
    ...
  completed/         # Archived tickets (status: done / cancelled / abandoned)
# Next number = max(existing XXXX dirs across .tickets/* and .tickets/completed/*) + 1. No counter file.
```

Numbers are four-digit zero-padded (`0001`, `0002`, ...). `status.md` format:
```
status: <stage>
ticket: XXXX
title: <short human-readable title>
branch: ticket/XXXX-<slug>
owner: <git config user.email>
source: local           # reserved seam — `github` etc. for externally-sourced tickets (not built)
external_id:            # reserved seam — e.g. github:#123
updated: YYYY-MM-DD
```

### Status transitions

| Status              | Set by                          | Transitions to                        |
|---------------------|---------------------------------|---------------------------------------|
| `claimed`           | `/problem` Phase 1 claim        | `solution`                            |
| `problem`           | `/problem` Phase 2              | `requirements`                        |
| `requirements`      | `/problem` Phase 3              | `solution`                            |
| `solution`          | `/problem` Phase 4; `/reopen` (from `completed/`) | `implementing`           |
| `implementing`      | `/build` setup                  | `review-ready`                        |
| `review-ready`      | `/build` after gate/repair loop — **branch only** | `done` or `implementing` |
| `changes-requested` | `/build` Step 7d, `review` skill — **branch only** | `implementing` (re-run `/build`) |
| `done`              | `/deliver` (ticket archived to `completed/`) | `solution` via `/reopen` |
| `cancelled`         | `/cancel` (ticket archived to `completed/`) | `solution` via `/reopen`  |
| `abandoned`         | `/abandon` or `/cancel --abandon` (terminal) | `solution` via `/reopen` |

> **Archive lifecycle:** `/deliver` and `/cancel` both move the ticket directory from `.tickets/<XXXX-slug>/` to `.tickets/completed/<XXXX-slug>/` after committing the terminal status. `/reopen XXXX` moves it back and sets `status: solution`. The `solution` status is therefore reachable from two paths: the forward design phase (`/problem`) and the reopen path (`/reopen`). After reopen, the lead must re-run `/build XXXX` before implementation resumes.

> **Self-speccing:** `/write-spec` never changed `status`; the `solution → implementing` transition has always been driven by `/build` setup. As of the merged build flow, `/build` also *generates* the spec/task files inline when it starts from `status: solution` with no specs present. `/write-spec` is therefore an optional pre-step, not a required transition.

### State split (multi-developer)

`main` carries the coarse, durable signal — `claimed`, `solution`, `implementing` (work started), and the terminal `done` / `cancelled` / `abandoned`. The fine implementation-phase states (`review-ready`, `changes-requested`) are **branch only**: committed inside the worktree and merged to `main` at `/deliver`. Because `/build` commits `implementing` to `main` and pushes *before* forking the worktree, only the branch advances `status.md` afterward, so the branch→main merge resolves `status.md` cleanly with no conflict.

`owner` (from `git config user.email`) is recorded at claim time. Number claiming is git-coordinated: a small `chore(ticket): XXXX claim` commit pushed first-wins; a loser re-numbers and retries. The `ticket.py` helper performs claims and transitions atomically (edit + scoped commit), and the `ticket_commit_guard` Stop hook blocks the turn if any tracked `.tickets/` file is left uncommitted.

**GitHub seam (reserved):** `source` / `external_id` exist so bug reports can later enter as tickets via GitHub Issues, behind the same `ticket.py` boundary. No network path is built in this iteration.

### Committing ticket metadata

`.tickets/` lives on `main` (only implementation code lives in the worktree — see **Worktrees** below). Every status transition **must be committed to `main`** so the ticket's state is durable (not local-only) and the history stays readable. Never leave `status.md` edits sitting uncommitted between commands.

After finalizing a transition, commit **only that ticket's metadata** — a scoped add, so unrelated working-tree changes are never swept in:

```
git add .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX → <status>"
```

For the archive step (after `/deliver` or `/cancel` sets the terminal status), the directory moves, so the commit uses a different pair of operations:

```
# After OS mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/
git rm -r --cached .tickets/XXXX-<slug>/
git add -- .tickets/completed/XXXX-<slug>/
git commit -m "chore(ticket): XXXX archive → completed/"
```

For `/reopen`, the reverse:

```
# After OS mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/
git rm -r --cached .tickets/completed/XXXX-<slug>/
git add -- .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX → solution (reopened)"
```

Rules:
- **One commit per transition.** Each command that writes `status.md` commits before it returns.
- **Scope the add** to the ticket directory — never `git add -A`. Lead-curated `_learnings.md` / `_standards.md` and unrelated edits stay out.
- `/problem` runs three transitions in one autonomous pass — it commits **once** at the end (`chore(ticket): XXXX design (status: solution)`), not three times.
- These metadata commits are separate from the worktree's implementation commits and from the `/deliver` merge commit. Expect, for a finished ticket: design commit → (worktree code commits, merged) → `→ review-ready` commit → `→ done` commit.

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

## Tech Stack Advisor

An optional sub-procedure that fires in `/problem` between Phase 3 (Requirements) and Phase 4 (Solution) when a new application, microservice, or UI component is detected. It is not triggered in `/build` or `/autopilot`.

**Trigger condition:** High-confidence new-artifact detection requires BOTH a keyword signal (`new`, `create`, `build`, `scaffold`, `greenfield` in the request) AND a manifest-absent signal (none of `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` at the project root). Either signal alone yields `feature-addition` classification and the advisor is skipped.

**Skip conditions:**
- `--no-stack-check` passed in the `/problem` invocation — advisor is bypassed entirely.
- `requirements.md` already contains a populated `## Tech Stack` section — advisor is bypassed; the existing stack is used as-is.

**`## Tech Stack` contract:** Once the advisor (or the lead manually) writes a `## Tech Stack` section into `requirements.md`, `/build` and `/autopilot` read and honor it without re-prompting the lead on subsequent runs.

**Rejection termination:** If the lead rejects the proposal twice without specifying an alternative (or provides two invalid responses, or one of each), the advisor writes the following placeholder and exits without blocking Phase 4:
```
<!-- stack not specified — fill in before /build -->
```

The full interaction protocol is in `context/flows/stack-advisor.md`.

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

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

| Status              | Set by                          | Commit target | Transitions to                        |
|---------------------|---------------------------------|---------------|---------------------------------------|
| `claimed`           | `/problem` Phase 1 claim        | **main**      | `solution`                            |
| `problem`           | `/problem` Phase 2              | branch only   | `requirements`                        |
| `requirements`      | `/problem` Phase 3              | branch only   | `solution`                            |
| `solution`          | `/problem` Phase 4; `/reopen` (onto a fresh branch) | branch only | `implementing`         |
| `implementing`      | `/build` setup (resumes the claim worktree) | branch only | `review-ready`            |
| `review-ready`      | `/build` after gate/repair loop | branch only   | `done` or `implementing`              |
| `changes-requested` | `/build` Step 7d, `review` skill | branch only  | `implementing` (re-run `/build`)      |
| `done`              | `/deliver` (folded into the squash commit) | **main** | `solution` via `/reopen` |
| `cancelled`         | `/cancel` (ticket archived to `completed/`) | **main** | `solution` via `/reopen`  |
| `abandoned`         | `/abandon` or `/cancel --abandon` (terminal) | **main** | `solution` via `/reopen` |

> **Two commits on `main` per ticket.** `main` carries **only** the `claimed` commit and one squashed delivery commit. Every state between — `problem`, `requirements`, `solution`, `implementing`, `review-ready`, `changes-requested` — is **branch only**: committed inside the claim-time worktree and pushed to origin, never committed to `main` before delivery. `main` therefore never re-touches a claimed ticket's `.tickets/<slug>/` until that ticket's own `/deliver`.

> **Archive lifecycle:** `/deliver` folds the `→ done` transition **and** the `.tickets/<slug>/ → completed/<slug>/` archive into the single `git merge --squash` commit (see **Squash delivery** below). `/cancel` and `/abandon` archive in their own separate terminal commit on `main`. `/reopen XXXX` forks a fresh branch from `main` HEAD and restores the dir from `completed/` onto that branch, setting `status: solution`. The `solution` status is therefore reachable from two paths: the forward design phase (`/problem`) and the reopen path (`/reopen`). After reopen, the lead must re-run `/build XXXX` before implementation resumes.

> **Self-speccing:** `/write-spec` never changed `status`; the `solution → implementing` transition has always been driven by `/build` setup. As of the merged build flow, `/build` also *generates* the spec/task files inline when it starts from `status: solution` with no specs present. `/write-spec` is therefore an optional pre-step, not a required transition.

### Ticket resolution

Every flow that reads a ticket's live status obeys one **worktree-first** rule. This is the single authoritative resolution rule; the resolver flows (`commands/autopilot.md`, `context/flows/build-ticket.md` Step 1, `context/flows/write-spec-ticket.md` Step 1, `commands/gate.md`, `context/flows/deliver-ticket.md` Step 1) cite it rather than re-deriving their own.

- **When a worktree `.worktrees/XXXX-<slug>` exists**, that worktree's `.tickets/XXXX-<slug>/` copy of `status.md` is **authoritative**. It carries every post-claim implementation-phase state — `solution`, `implementing`, `review-ready`, `changes-requested` — because those states are branch-only (see **Two commits on `main`** above).
- **The root `.tickets/XXXX-<slug>/` copy** (the one on `main`) signals only the coarse **claim and terminal** states: it reads `claimed` from claim until delivery, then `done` / `cancelled` / `abandoned`. Between claim and delivery it is deliberately stale and must **not** be trusted for the implementation-phase status.

So a resolver: (1) locates the ticket dir (`.tickets/XXXX-*`, else `.tickets/completed/XXXX-*`); (2) if `.worktrees/XXXX-<slug>` exists, reads the worktree copy of `status.md`, otherwise the root copy; (3) applies its precondition against that authoritative status.

**Worked example.** A ticket claimed and designed to `solution`:

- `main`'s `.tickets/0042-foo/status.md` → `status: claimed` — the stale claim stub.
- `.worktrees/0042-foo/.tickets/0042-foo/status.md` → `status: solution` — authoritative.

A resolver that reads the root copy would see `claimed` and wrongly reject a correctly-designed ticket; it must read the worktree copy whenever the worktree exists. (Legacy tickets claimed before branch-at-claim may have no worktree; there the root copy is authoritative until `/build` resumes or recreates one.)

### State split (multi-developer)

`main` carries only the coarse, durable signal — the `claimed` commit and the terminal `done` / `cancelled` / `abandoned`. **All** post-claim implementation-phase states (`solution`, `implementing`, `review-ready`, `changes-requested`) are **branch only**: committed inside the claim-time worktree and pushed to origin, never to `main`. Because `main` never re-touches a claimed ticket's `.tickets/<slug>/` after the claim stub, the delivery `git merge --squash`'s merge base for that path is the claim stub and only the branch changed it — so the path resolves cleanly with no conflict, and the whole branch (code + the branch's `.tickets/<slug>/`) collapses into one commit.

The branch `ticket/XXXX-<slug>` and worktree `.worktrees/XXXX-<slug>` are created at **claim time** (`/problem` Phase 1) — but only **after** the claim push wins, so a renumber-on-reject leaves no orphaned branch or worktree. The worktree's lifecycle therefore spans `/problem` → `/build` → `/deliver`. `/build` **resumes** that pre-existing worktree rather than creating one.

`owner` (from `git config user.email`) is recorded at claim time. Number claiming is git-coordinated: a small `chore(ticket): XXXX claim` commit pushed first-wins; a loser re-numbers and retries. The `ticket.py` helper performs claims and transitions atomically (edit + scoped commit + push of the branch), encapsulates the squash delivery in `deliver_squash()`, and the `ticket_commit_guard` Stop hook blocks the turn if any tracked `.tickets/` file is left uncommitted — scanning the main root **and** every active worktree (discovered via `git worktree list`, anchored on `git rev-parse --git-common-dir`) so a branch-only edit can't be left dangling either.

### Squash delivery

`/deliver` merges the feature branch with `git merge --squash` (not `--no-ff`), producing exactly one "completed work" commit on `main` that contains the entire branch diff — no per-worktree-commit history and no merge commit. The `→ done` transition and the `completed/<slug>/` archive are folded into that **same** commit. The sequence (`ticket.py deliver_squash()`) mirrors the archive pattern — `git merge --squash`, then OS `mv` + `git rm -r --cached` + `git add` (never `git mv`, which is unsound against the index a squash leaves) — then one commit, push, and removal of the worktree + branch. A reopened ticket forks a fresh branch and adds a **further** squashed commit on re-delivery.

**GitHub seam (reserved):** `source` / `external_id` exist so bug reports can later enter as tickets via GitHub Issues, behind the same `ticket.py` boundary. No network path is built in this iteration.

### Committing ticket metadata

The **claim** stub (`status: claimed`, carrying `title` / `owner` / `branch`) is committed and pushed to `main` — the only `main` commit a ticket writes before delivery. **After the claim**, the ticket directory lives on the feature branch inside the worktree: every status transition **and** every artifact write (`problem.md`, `requirements.md`, `solution.md`, spec/task files, implementation) is committed to the **branch and pushed to origin**, never to `main`. Never leave `status.md` edits sitting uncommitted between commands.

After finalizing a transition, commit **only that ticket's metadata** — a scoped add, so unrelated working-tree changes are never swept in. On the branch, use the helper so the commit and the branch push are atomic:

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX <status> --push
```

which is equivalent to a scoped `git add .tickets/XXXX-<slug>/` + `git commit` + a push of the current branch (setting upstream on first push).

`/deliver` folds the terminal `→ done` and the archive into the single squash commit (see **Squash delivery**). For `/cancel` and `/abandon`, the directory moves to `completed/` in a separate terminal commit on `main`:

```
# After OS mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/
git rm -r --cached .tickets/XXXX-<slug>/
git add -- .tickets/completed/XXXX-<slug>/
git commit -m "chore(ticket): XXXX archive → completed/"
```

For `/reopen`, the reverse, committed **on the fresh branch** (not `main`):

```
# After OS mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/
git rm -r --cached .tickets/completed/XXXX-<slug>/
git add -- .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX → solution (reopened)"
```

Rules:
- **One commit per transition.** Each command that writes `status.md` commits before it returns, and pushes the branch it lives on.
- **Scope the add** to the ticket directory — never `git add -A`. Lead-curated `_learnings.md` / `_standards.md` and unrelated edits stay out.
- `/problem` writes the design artifacts on the branch and commits+pushes them there (e.g. `chore(ticket): XXXX design (status: solution)`) — no design commit ever lands on `main`.
- Expect, for a finished ticket, exactly **two** `main` commits: the `claim` commit and the squashed delivery commit. All design, implementation, and intermediate-status commits live on the branch (pushed) and collapse into that one delivery commit.

---

## Worktrees

- **Branch naming**: `ticket/XXXX-<slug>`
- **Worktree location**: `.worktrees/XXXX-<slug>` — globally git-ignored
- **Created at claim time** (`/problem` Phase 1), only after the claim push wins, so the design phase has a branch to write to and a renumber leaves no orphan. The worktree's lifecycle spans `/problem` → `/build` → `/deliver`; `/build` resumes it.
- All design artifacts **and** implementation live on the branch in the worktree. **Never commit them to `main` directly** — only the `claim` commit and the squashed delivery commit touch `main`.
- The branch is squash-merged to `main` at `/deliver`, then the worktree is removed and the branch deleted.

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
| `.tickets/_learnings.md` | Lead-curated | `/deliver` and `/harvest-learnings` (append-only, after lead approval) | Loaded at `/problem` and `/build` | Human-curated must-fix patterns. |
| `.tickets/_standards.md` | Lead only | The lead, by hand | Loaded at `/problem` and `/build` | Project engineering standards. |

`/deliver` and `/harvest-learnings` **append** candidate learnings to `_learnings.md`, but only after the lead accepts them and only via a template-field-only write path (`date | gate | ticket | pattern`) — never raw extracted text, and never overwriting existing content. `/init` creates both files as stubs.

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

---

## Progress checklist

Every multi-stage flow (one that runs more than one named stage before returning to the lead) shows its progress as a live checklist so the lead can always see where the run is. The mechanism is **instruction-based** — there is no hook that injects it; reliability comes from making it the flow's first action.

Convention:

- **First action.** Before executing the flow's first step, call `TodoWrite` to create a checklist with exactly one item per stage the flow declares in its own "Progress checklist" block (the labels after the `<!-- progress-checklist -->` sentinel).
- **One `in_progress`.** Mark a stage `in_progress` when you start it and `completed` when you finish it. Keep exactly one item `in_progress` at a time.
- **Short labels.** Use the flow's declared labels verbatim — they are kept to a few words so they survive UI truncation. Do not paraphrase or expand them.
- **True state on early exit.** If the flow stops early (escalation, a blocking question, an error), leave the checklist reflecting the true state — the stage that was running stays `in_progress`, later stages stay pending. Never mark `completed` work that did not finish.
- **One list per run.** A flow entered as a **sub-flow** under a parent flow does **not** create its own checklist. The parent already declared the full run's stages and created the list; the sub-flow adopts that existing list and advances the stages it owns. Concretely, `build-ticket.md` and `deliver-ticket.md` run as sub-flows under `/autopilot` — under autopilot they advance the autopilot run's checklist rather than creating a second one. The observable trigger is simply whether a checklist already exists for this run.

Each multi-stage flow carries its own "Progress checklist" block at the top (before its first step), opening with the `<!-- progress-checklist -->` sentinel, declaring its stage labels, and pointing back to this convention. Labels shared across flows are byte-identical so a sub-flow's stages line up with the parent's.

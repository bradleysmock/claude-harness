# Harness Reference

Operational details for the harness-combined pipeline. Loaded on demand — not in every session context.

---

## Tickets

All SDLC work is tracked under `.tickets/`.

```
.tickets/
  .ticket.lock       # `claim()` acquires/releases this itself (atomic O_CREAT|O_EXCL, rename-verify steal) — path and pid:epoch format unchanged
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
depends-on: 0010, 0011  # optional — comma-separated 4-digit ticket numbers this ticket depends on
updated: YYYY-MM-DD
```

### Ticket dependencies (`depends-on:`)

`status.md` may carry an **optional** `depends-on:` line whose value is a
comma-separated list of four-digit ticket numbers (e.g. `depends-on: 0010, 0011`).
Its **absence is treated identically to an empty list** — no migration is needed
for pre-existing tickets. All ticket numbers are **normalized to 4-digit
zero-padded strings** on parse, so `depends-on: 10, 11` and `depends-on: 0010, 0011`
are equivalent.

The parsing, validation, and graph logic live in `ticket_deps.py` (I/O layer +
graph layer), which the flow docs delegate to:

- **`parse_deps(tickets_root)`** — scans both `.tickets/` and `.tickets/completed/`
  (so a ticket may depend on an already-completed one), contains every scanned
  path within the tickets root (fail-closed path-traversal guard), and returns a
  frozen `TicketGraph`.
- **`check_cycle(graph)` / `assert_acyclic(graph)`** — DFS cycle detection
  (O(N+E)); a cycle raises `TicketCyclicDependencyError` (a `ValueError` subclass)
  whose message names the full cycle path.
- **`assert_acyclic_with_proposed(tickets_root, proposed)`** — the write-time guard
  used by `/problem` Phase 4: it overlays the about-to-be-written `TicketInfo` onto
  the loaded graph before checking, so a cycle or unknown reference introduced by the
  edge being authored is caught *before* it is persisted (a plain `assert_acyclic`
  over on-disk state would miss it).
- **`blocking_dependencies(graph, ticket)`** — the dependencies of `ticket` not
  yet in `done` status; a non-empty result blocks `/build`.
- **`topo_layers(graph)`** — Kahn topological execution waves.
- **`mermaid_diagram(graph)`** — a Mermaid `graph TD` diagram; labels are
  sanitized via the `MERMAID_UNSAFE_CHARS` constant.

**Cycle detection runs whenever `status.md` is written with a `depends-on:` field**
— at design-write time in `/problem` Phase 4 and at any subsequent status
transition in `/build` — and rejects the write before completing it. A
`depends-on:` reference to a ticket that exists in neither `.tickets/` nor
`.tickets/completed/` is a validation error (`ValueError`), not silently ignored.

### Status transitions

| Status              | Set by                          | Commit target | Transitions to                        |
|---------------------|---------------------------------|---------------|---------------------------------------|
| `claimed`           | `/problem` Phase 1 claim        | **`harness-tickets` ledger** (+ stub on branch) | `solution` |
| `problem`           | `/problem` Phase 2              | branch only   | `requirements`                        |
| `requirements`      | `/problem` Phase 3              | branch only   | `solution`                            |
| `solution`          | `/problem` Phase 4; `/reopen` (onto a fresh branch) | branch only | `implementing`         |
| `implementing`      | `/build` setup (resumes the claim worktree) | branch only | `review-ready`            |
| `review-ready`      | `/build` after gate/repair loop | branch only   | `done` or `implementing`              |
| `changes-requested` | `/build` Step 7d, `review` skill | branch only  | `implementing` (re-run `/build`)      |
| `done`              | `/deliver` (folded into the squash commit) | **main** (+ `delivered` ledger event) | `solution` via `/reopen` |
| `cancelled`         | `/cancel` (docs archived onto `harness-tickets`) | **`harness-tickets` ledger** (main-free) | `solution` via `/reopen`  |
| `abandoned`         | `/abandon` or `/cancel --abandon` (terminal) | **`harness-tickets` ledger** (main-free) | `solution` via `/reopen` |

> **One commit on `main` per ticket — the delivery squash.** Ticket-number
> allocation and the coarse lifecycle log (`claim` / `delivered` / `cancelled` /
> `abandoned` / `reopened`) live on a dedicated orphan **`harness-tickets`**
> branch (an append-only `ledger.jsonl`; the design calls it `.harness-tickets`,
> but a git ref may not begin with a dot, so the on-disk branch drops it). `main`
> receives **nothing** before a ticket's `/deliver`: the claim writes only a
> ledger line + a branch stub, and every state between — `problem`,
> `requirements`, `solution`, `implementing`, `review-ready`,
> `changes-requested` — is **branch only**. `main`'s history is therefore product
> code plus one squash per delivered ticket, with no coordination churn.

> **The `harness-tickets` ledger is the number arbiter.** Next number =
> `max(claim.number) + 1` over `ledger.jsonl`. Every mutation commits **and
> pushes** to origin before returning (§1a push invariant): `origin`'s ref *is*
> the coordination point, so a local-only append reserves nothing. A rejected
> `claim` push renumbers against the newer ledger and retries; other events
> rebase the append and retry with the same number. The `harness-tickets` branch
> is **never merged into `main`**.

> **Archive lifecycle:** `/deliver` folds the `→ done` transition **and** the
> `.tickets/<slug>/ → completed/<slug>/` archive into the single `git merge
> --squash` commit (see **Squash delivery** below) and appends a `delivered`
> ledger event. `/cancel` and `/abandon` are **main-free**: they append a
> `cancelled`/`abandoned` ledger event, archive the ticket docs onto
> `harness-tickets` (under `cancelled/<slug>/` / `abandoned/<slug>/`), and delete
> the branch + worktree — no terminal commit on `main`. `/reopen XXXX` forks a
> fresh branch from `main` HEAD and restores the dir from its archive (`main`'s
> `completed/` for a delivered ticket, `harness-tickets` for a cancelled one),
> setting `status: solution` and appending a `reopened` ledger event. The
> `solution` status is therefore reachable from two paths: the forward design
> phase (`/problem`) and the reopen path (`/reopen`). After reopen, the lead must
> re-run `/build XXXX` before implementation resumes.

> **Self-speccing:** `/write-spec` never changed `status`; the `solution → implementing` transition has always been driven by `/build` setup. As of the merged build flow, `/build` also *generates* the spec/task files inline when it starts from `status: solution` with no specs present. `/write-spec` is therefore an optional pre-step, not a required transition.

### Ticket resolution

Every flow that reads a ticket's live status obeys one **worktree-first** rule. This is the single authoritative resolution rule; the resolver flows (`commands/autopilot.md`, `context/flows/build-ticket.md` Step 1, `context/flows/write-spec-ticket.md` Step 1, `commands/gate.md`, `context/flows/deliver-ticket.md` Step 1) cite it rather than re-deriving their own.

- **When a worktree `.worktrees/XXXX-<slug>` exists**, that worktree's `.tickets/XXXX-<slug>/` copy of `status.md` is **authoritative**. It carries every post-claim implementation-phase state — `solution`, `implementing`, `review-ready`, `changes-requested` — because those states are branch-only (see **One commit on `main`** above).
- **For an in-flight ticket there is no root `.tickets/XXXX-<slug>/` copy on `main`** — the dir lives only on the feature branch until delivery. The coarse **claim** state comes from the `harness-tickets` ledger; a remote in-flight ticket owned by another dev is read from its pushed branch (`git show ticket/XXXX-<slug>:.tickets/XXXX-<slug>/status.md`), which the ledger's `branch` field names. After delivery the dir is on `main` under `completed/XXXX-<slug>/` (`done`).

So a resolver: (1) locates the ticket dir — the worktree `.worktrees/XXXX-*`, else `main`'s `.tickets/completed/XXXX-*` (delivered); (2) reads the worktree copy of `status.md` when a worktree exists, otherwise the completed copy; (3) the ledger supplies the coarse `claimed`/terminal state for tickets with no local checkout.

**Worked example.** A ticket claimed and designed to `solution`:

- `main` has **no** `.tickets/0042-foo/` — nothing about the in-flight ticket touches `main`.
- The `harness-tickets` ledger has `{"event":"claim","number":42,…}` — the coarse claim.
- `.worktrees/0042-foo/.tickets/0042-foo/status.md` → `status: solution` — authoritative fine status.

A resolver reads the worktree copy whenever the worktree exists; for a remote-owned ticket with no local worktree it reads the pushed branch named by the ledger's `branch` field.

### State split (multi-developer)

`main` carries only the durable product record — the squashed delivery commit (`done`, under `completed/`). The **coarse** lifecycle (`claim` / `delivered` / `cancelled` / `abandoned` / `reopened`) lives on the `harness-tickets` ledger; the **fine** implementation-phase states (`solution`, `implementing`, `review-ready`, `changes-requested`) are **branch only**, committed inside the claim-time worktree and pushed to origin, never to `main`. Because `main` never held a claim stub, the delivery `git merge --squash` sees the branch's `.tickets/<slug>/` as a pure addition — no stale stub to reconcile — and the whole branch (code + the branch's `.tickets/<slug>/`) collapses into one commit.

The branch `ticket/XXXX-<slug>` and worktree `.worktrees/XXXX-<slug>` are created at **claim time** (`/problem` Phase 1) — but only **after** the ledger claim push wins, so a renumber-on-reject leaves no orphaned branch or worktree. The worktree's lifecycle therefore spans `/problem` → `/build` → `/deliver`. `/build` **resumes** that pre-existing worktree rather than creating one.

`owner` (from `git config user.email`) is recorded on the claim's ledger line. Number claiming is git-coordinated on `harness-tickets`: a `claim` event appended to `ledger.jsonl` and pushed first-wins; a loser re-numbers against the newer ledger and retries. The `ticket.py` helper performs claims and transitions atomically (ledger append + push, then branch stub), encapsulates the squash delivery in `deliver_squash()`, and the `ticket_commit_guard` Stop hook blocks the turn if any tracked `.tickets/` file is left uncommitted — scanning the main root **and** every active worktree (discovered via `git worktree list`, anchored on `git rev-parse --git-common-dir`) — **or** if a local `harness-tickets` ledger commit is left unpushed to origin (an unpublished number reservation that would collide).

### Squash delivery

`/deliver` merges the feature branch with `git merge --squash` (not `--no-ff`), producing exactly one "completed work" commit on `main` that contains the entire branch diff — no per-worktree-commit history and no merge commit. This is the **first and only** time `main` sees the ticket. The `→ done` transition and the `completed/<slug>/` archive are folded into that **same** commit. The sequence (`ticket.py deliver_squash()`) mirrors the archive pattern — `git merge --squash`, then OS `mv` + `git rm -r --cached` + `git add` (never `git mv`, which is unsound against the index a squash leaves) — then one commit, push `main` **first** (the durable record), then append a `delivered` ledger event (idempotent by `(event, number)`, so a ledger race never blocks delivery), then removal of the worktree + branch. A reopened ticket forks a fresh branch and adds a **further** squashed commit on re-delivery.

**GitHub seam (reserved):** `source` / `external_id` exist so bug reports can later enter as tickets via GitHub Issues, behind the same `ticket.py` boundary. No network path is built in this iteration.

### Committing ticket metadata

The **claim** appends a `claim` line to the `harness-tickets` ledger (pushed first-wins) and writes the `status: claimed` stub (carrying `title` / `owner` / `branch`) **on the feature branch** inside its worktree — **nothing lands on `main`**. From the claim onward the ticket directory lives on the branch: every status transition **and** every artifact write (`problem.md`, `requirements.md`, `solution.md`, spec/task files, implementation) is committed to the **branch and pushed to origin**, never to `main`. Never leave `status.md` edits sitting uncommitted between commands, and never leave a `harness-tickets` ledger commit unpushed.

After finalizing a transition, commit **only that ticket's metadata** — a scoped add, so unrelated working-tree changes are never swept in. On the branch, use the helper so the commit and the branch push are atomic:

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX <status> --push
```

which is equivalent to a scoped `git add .tickets/XXXX-<slug>/` + `git commit` + a push of the current branch (setting upstream on first push).

`/deliver` folds the terminal `→ done` and the `completed/<slug>/` archive into the single squash commit (see **Squash delivery**) and appends a `delivered` ledger event. `/cancel` and `/abandon` are **main-free**: the helper appends a `cancelled`/`abandoned` ledger event, archives the ticket docs onto `harness-tickets`, and deletes the branch + worktree — no terminal commit on `main`:

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" cancel XXXX --push    # or: abandon
```

For `/reopen`, a fresh branch is forked from `main` HEAD and the dir is restored from its archive (`main`'s `completed/` for a delivered ticket via `git rm -r --cached` + `git add`, or `harness-tickets` for a cancelled one), committed **on the fresh branch** (not `main`) at `status: solution`, plus a `reopened` ledger event:

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" reopen XXXX --push
```

Rules:
- **One commit per transition.** Each command that writes `status.md` commits before it returns, and pushes the branch it lives on.
- **Scope the add** to the ticket directory — never `git add -A`. Lead-curated `_learnings.md` / `_standards.md` and unrelated edits stay out.
- `/problem` writes the design artifacts on the branch and commits+pushes them there (e.g. `chore(ticket): XXXX design (status: solution)`) — no design commit ever lands on `main`.
- Expect, for a finished ticket, exactly **one** `main` commit: the squashed delivery commit. All coordination (claim, terminal events) lives on the `harness-tickets` ledger; all design, implementation, and intermediate-status commits live on the branch (pushed) and collapse into that one delivery commit.

---

## Worktrees

- **Branch naming**: `ticket/XXXX-<slug>`
- **Worktree location**: `.worktrees/XXXX-<slug>` — globally git-ignored
- **Created at claim time** (`/problem` Phase 1), only after the ledger claim push wins, so the design phase has a branch to write to and a renumber leaves no orphan. The worktree's lifecycle spans `/problem` → `/build` → `/deliver`; `/build` resumes it.
- All design artifacts **and** implementation live on the branch in the worktree. **Never commit them to `main` directly** — only the squashed delivery commit touches `main`.
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

#### Directory-mode test gate: full suite + baseline-delta (all four languages)

In **directory mode** the `test` gate runs the **entire** suite and fails only on
failures that are **not** already present at the merge base — the *baseline-delta*
mechanism. It runs the full suite (Python `pytest -rA`, TypeScript `jest --json`,
Go `go test -json`, Rust `cargo test`), collects stable per-test IDs
(`path::test`, `pkg.TestName`, `crate::mod::test`), and subtracts the set of tests
already failing at the merge base. That baseline is computed **once per merge-base
SHA** in a throwaway detached `git worktree` (never touching the ticket worktree)
and cached under `.harness/test-baselines/<sha>.json`. What remains gates the
ticket; pre-existing merge-base failures are reported as `baseline_excluded` lines
(informational, not failures). A previously-passing test that is **deleted** in the
worktree (`pass→removed`) is also flagged as a regression. When git is absent or the
merge base is unknown, the gate falls back to **strict full-suite** (every failure
fails — fail-closed). The `GateResult` records `mode` (`full` | `baseline-delta`)
and `baseline_excluded`, surfaced in `gate-findings.md`. Ticket 0041 shipped this
for TypeScript; the shared engine (`gates/_baseline.py`) now applies it uniformly to
Python, Go, and Rust as well, so an unrelated already-red test never blocks a
polyglot ticket in one language while being tolerated in another. When such a
delta failure is later repaired, the flow records it via
`memory(action="record", gate="test", outcome="passed", resolution=…)` so the fix
joins the failure corpus.

In **directory mode**, after the language suite (and the coverage and dep-audit
phases) a final **`sast`** phase runs: Semgrep across all languages plus Bandit
for Python, with severity-tiered results (HIGH → BLOCKER fails the gate;
MEDIUM/LOW → MAJOR/MINOR warnings). It reads a project-owned `.semgrep.yml` /
`bandit.ini` when present (contained within the project root) and otherwise falls
back to Semgrep's `p/default` ruleset with a floating-ruleset warning. When
neither tool is installed the phase skips cleanly and passes with a "SAST
skipped" warning. Findings are written to `gate-findings.md` under a
`# SAST — gate-findings` section in the shared bullet format. The `sast` phase is
the severity-tiered, full-directory security scan; it **complements** the per-file
Bandit run in `post_write_gate` (fast write-time feedback) rather than replacing
it.

> **Fail-fast bypass (known limitation):** because the directory suite is
> fail-fast and `sast` runs last, a failing lint/type/test gate short-circuits
> the run before `sast` executes. Fix earlier-phase failures to surface SAST
> findings. Pin `.semgrep.yml` to avoid `p/default` rule churn.

### Hook ↔ MCP gate command parity

The write-time hooks and the MCP gate must enforce the **same** commands per
language, or the same code gets inconsistent signals (e.g. a data race that
passes the turn-end hook but fails the `-race` MCP gate). The per-language
commands are documented below and locked by a drift test
(`tests/test_0052_hook_gate_drift.py`), which parses this table and asserts the
documented commands still match the hook and gate source. Update this table and
the source together; the drift test fails if they diverge.

| Language   | Per-write hook (`post_write_gate`) | Stop hook (`stop_full_gate`)                                   | MCP gate (`gates/`)                              |
|------------|------------------------------------|----------------------------------------------------------------|--------------------------------------------------|
| Python     | `ruff check`, `bandit -ll`         | `ruff check`, `bandit -ll`, `mypy`, `pytest -q`                 | `ruff`, `mypy`, `bandit`, `pytest`               |
| JS/TS      | `npx --no-install eslint`          | `npx --no-install eslint`, `npx --no-install tsc --noEmit`, `npm test` | `eslint`, `tsc --noEmit`                  |
| Go         | `gofmt -l`                         | `gofmt -l`, `go vet ./...`, `go test -race ./...`              | `go vet`, `go test -race -v ./...`               |
| Rust       | `rustfmt --check`                  | `cargo fmt --check`, `cargo clippy`, `cargo test`             | `cargo check`, `cargo clippy`, `cargo test`      |

The Go row is the parity that motivated this table: both the Stop hook and the
MCP gate run `go test` with `-race`, so a data race cannot pass one layer and
fail the other. The per-write hook resolves `eslint` through
`npx --no-install` from the written file's project root (nearest `package.json`),
matching the Stop hook, so project-local eslint installs actually lint on write.

### Parallel gate execution (`parallel_gate_limit`)

In **directory mode** the language gates run through a dependency-aware scheduler
(`gates/scheduler.py`). Independent gates run concurrently on a thread pool while a
gate with a declared prerequisite waits for it to pass — per language,
`gates/gate_graph.py` declares `test` depends on `type_check` (Python/TypeScript),
`build` (Go) or `check` (Rust); every other gate is independent. Result ordering is
always the language's declared order, so `gate-findings.md` is unchanged.

- **Opt-in, per project.** Add a `parallel_gate_limit = N` line to the `[gates]`
  block of `.tickets/_standards.md` (the same block that holds command overrides).
  `N` is the max gates in flight at once. Absent the key, the suite stays
  **sequential** (identical to the pre-0036 fail-fast loop) — parallelism does not
  turn on until the lead sets a limit. `parallel_gate_limit = 1` is explicitly
  sequential; a malformed value fails closed with a `CONFIG_ERROR` finding.
- **Prerequisite failure skips dependents.** If `type_check` fails, `test` is
  recorded as a `SKIPPED` result (not silently passed).
- **`fail_fast` semantics.** Under fail-fast a gate failure stops *new* gate
  submissions; gates already in flight run to completion and their results are
  captured. At `parallel_gate_limit = 1` this reproduces the old early-return exactly.
- **Per-gate logs, written on completion (caveat).** When a log directory is
  supplied, each gate's rendered result is written to `<log_dir>/<gate>.log` once the
  gate finishes — not streamed incrementally. A gate process killed mid-run (e.g.
  SIGKILL) therefore leaves no log for itself, but its peers' logs are intact. The
  gate name is validated as a safe single path component before the path is built.

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
| `.harness/memory.db` | Machine only (opaque) | `memory(action="record", ...)` after each gate cycle (threading `target_file`) | `memory(action="retrieve", ...)` before each repair attempt **and** `memory(action="gotchas", ...)` before generation | BM25-searchable failure trail. |
| `.tickets/_learnings.md` | Lead-curated | `/deliver` and `/harvest-learnings` (append-only, after lead approval) | Loaded at `/problem` and `/build` | Human-curated must-fix patterns. |
| `.tickets/_standards.md` | Lead only | The lead, by hand | Loaded at `/problem` and `/build` | Project engineering standards. |

`/deliver` and `/harvest-learnings` **append** candidate learnings to `_learnings.md`, but only after the lead accepts them and only via a template-field-only write path (`date | gate | ticket | pattern`) — never raw extracted text, and never overwriting existing content. `/init` creates both files as stubs.

**`memory.db` is consulted in two directions** — reactive and proactive:

- **Reactive** (`action="retrieve"`): keyed on the failing gate's **error text**, fired *inside* the repair loop after a gate fails. Surfaces BM25-similar past failures (and their `resolution`) to guide the fix. Unchanged.
- **Proactive** (`action="gotchas"`): keyed on the spec's **domain signals** — `target_file` + `description` + `language` — fired *before* generation, so the first attempt pre-empts known area-local failure modes. Returns only `outcome='passed'` (resolved) records, fenced to the language's gates, ranked by area proximity (exact `target_file`, then same directory) with a BM25 tiebreaker over the description, each carrying its stored `resolution` (the known fix). Returns an empty block when nothing is relevant. This is why `record` now threads `target_file`: without it a record is retrievable only by the reactive error-keyed path.

Both directions read the same opaque trail; neither ever writes to the lead-curated `_learnings.md` / `_standards.md`.

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

### Severity tiers

Canonical 4-tier vocabulary, worded to be usable verbatim by design review, code review, and standalone diff critique — the same tiers `critique`, `review`, and the critic subagent all apply:

- **BLOCKER** — serious design problem likely to cause bugs, maintenance failure, or security issues. Blocks the next checkpoint (design approval or merge).
- **MAJOR** — clear violation of a principle with meaningful consequences. Fix now, or open a new ticket if the effort is large.
- **MINOR** — improvement opportunity. Fix if the code is being touched anyway; otherwise logged.
- **OBS** — observation worth noting. May reflect a legitimate tradeoff. Logged only.

Must-fix vs. optional differs by review path:

- **`/build` post-build critic** — BLOCKER **and** MAJOR are must-fix and trigger the auto-repair loop (Step 7a); `changes-requested` fires only when that loop is exhausted. MINOR / OBS are optional — listed for the lead, never auto-fixed.
- **`review` skill (interactive)** — `changes-requested` fires on BLOCKER findings; MAJOR / MINOR / OBS appear in the report for the lead to decide on.

### Critic findings file (`critic-findings.md`)

The post-build critic's report is not only displayed — it is **persisted** to a
per-ticket `critic-findings.md`, the durable sibling of `gate-findings.md`, at
`.tickets/XXXX-<slug>/critic-findings.md`.

- **Append-only, per-round sections.** `/build` Step 7 (round 1) and every
  auto-repair round (Step 7a) append the round's structured report to the file,
  each section headed by its round number and date (e.g. `## Round 2 — 2026-07-06`).
  `repair-escalation.md` Phase 1 appends the diagnostic subagent's output (root
  cause, fix strategy, target locations) as its own section. Nothing is ever
  rewritten or truncated in place — the file is the run's durable critic history.
- **Committed on the branch with each round.** Each append is committed inside the
  worktree alongside the repair commit for that round; it never touches `main`
  until the delivery squash archives it with the rest of the ticket.
- **Consumed downstream.** `/deliver` Step 5 scans it (alongside `gate-findings.md`)
  for candidate learnings; the `review` and `debug` skills read it when present and
  cite prior rounds instead of re-deriving them.
- The machine-readable counterpart is `.harness/memory.db`: escalated repair loops
  and escalation diagnoses are also recorded via `memory(action="record", ...)`
  under gate `"critic"` (diagnosis) or outcome `"escalated"` (exhausted loop), so
  BM25 retrieval can warn a future repair away from an approach that already failed.

---

## Craft Polish Pass

After functional acceptance — the critic's BLOCKER/MAJOR must-fix loop has cleared (or there were none) — `/build` runs a **craft polish pass** (`build-ticket.md` Step 7b.5). It is **ticket-mode only**: spec/standalone mode has no critic loop and is out of scope. It improves craft (naming, decomposition, restraint, load-bearing comments) **without changing behaviour**, and enforces that mechanically.

- **The `craft` subagent** (`agents/craft.md`) is read-only-reasoning, modeled on the critic (asymmetric exposure — no implementer reasoning framing). It emits structured JSON — `reasoning`, `improvements[]` (`{category, location_hint, rationale}`), `polished_implementation`, `polished_tests` — where every improvement falls into exactly one of a bounded seven-value taxonomy (`rename | extract | inline | comment | delete | simplify | error_handling`) and cites a specific identifier or line. It never proposes behaviour changes: **behaviour must not change.**
- **Gate-lock (behaviour preservation).** Before the loop, the pass pins the pre-polish HEAD SHA and the pre-polish test files. Each round: spawn the subagent, apply its output, then (a) re-run `gate_run_on_dir(worktree, "auto", project_root)` — reverting the round on any new failure or 0041 baseline regression — and (b) run the **pinned pre-polish tests** against the polished implementation (the `CRAFT_REQUIRE_TEST_SURVIVAL` anti-cheat guard) — reverting the round if any pinned test fails. This blocks the polisher from weakening a test to pass the gate, which the critic already treats as a BLOCKER. Reuses the existing gate machinery — no new gate runner.
- **Per-round commits.** Each accepted round is its own commit (`polish: craft round N`), so the lead sees craft changes as a distinct, revertable slice in the Step 6 diff, never entangled with the functional implementation.
- **Config.** `CRAFT_MAX_ITERATIONS` (default 3; `0` disables the pass — worktree returned unchanged) and optional `CRAFT_REQUIRE_TEST_SURVIVAL` (default true) live in `.harness/config.py`, declared alongside `MAX_REPAIR_ATTEMPTS`.
- **Terminal statuses.** The loop ends with `final_status` = `converged` (subagent returned empty `improvements`), `max_iterations_reached` (hit `CRAFT_MAX_ITERATIONS` still proposing), or `disabled` (`CRAFT_MAX_ITERATIONS == 0`).
- **Report.** A `CraftPolishReport` (`iterations_run`, `improvements_applied[]`, `improvements_rejected[]`, `final_status`) is written to `.harness/craft/<ticket>.json` — the transient, git-ignored sibling of `.harness/results/` and `.harness/critiques/`. The `craft.*` instrumentation is emitted as deterministic status lines (`started` / `iteration` / `improvement_applied` / `improvement_rejected` / `completed`), not an event bus.

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

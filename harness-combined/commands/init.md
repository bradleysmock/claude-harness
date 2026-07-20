Initialize the harness pipeline in the current project.

## Steps

### 1 — Create harness directory structure

```
.harness/
├── specs/        ← spec files go here
├── tasks/        ← task DAG files go here
├── results/      ← run artifacts go here
├── critiques/    ← /critique reports go here (git-ignored like the rest of .harness/)
├── craft/        ← craft-polish reports (.harness/craft/<ticket>.json) go here (git-ignored)
└── checkpoints/  ← task resume state
.tickets/         ← SDLC ticket directory (active tickets live here)
.tickets/completed/ ← archived tickets (status: done or cancelled)
.worktrees/       ← git worktrees (auto-gitignored)
```

### 2 — Write `.harness/config.py`

```python
# Harness configuration
# language: python | typescript | go | rust | auto
LANGUAGE = "auto"

# Root of the project (used for PYTHONPATH injection and file resolution)
PROJECT_ROOT = "."

# Maximum repair attempts before escalating
MAX_REPAIR_ATTEMPTS = 3

# Maximum craft-polish iterations after critic acceptance (ticket mode).
# 0 disables the craft polish pass entirely (worktree returned unchanged,
# final_status="disabled").
CRAFT_MAX_ITERATIONS = 3

# When true, each polish round re-runs the pinned pre-polish tests against the
# polished implementation and reverts the round if any fail (the anti-cheat /
# test-survival guard). Optional; default true.
CRAFT_REQUIRE_TEST_SURVIVAL = True
```

### 3 — Write `.tickets/NEXT_TICKET`

```
0001
```

### 4 — Add harness paths to `.gitignore`

Ensure each of these entries is present in `.gitignore` (append any that are missing; create the file if absent):

```
.harness/            # machine-local scaffolding: specs, tasks, results, critiques, checkpoints, memory.db
.worktrees/          # git worktrees
.tickets/.active     # transient active-ticket sentinel
.tickets/.ticket.lock # transient ticket-number claim lock
```

`.harness/` is machine-local scaffolding and is ignored **wholesale** — so `results/`, `critiques/` (the `/critique` reports), `craft/` (the craft-polish reports), `checkpoints/`, and the `memory.db` failure trail all stay out of git under the same rule; none of them should ever land in a commit. `.tickets/` itself (status.md, problem/requirements/solution.md, NEXT_TICKET, the lead-curated `_standards.md` / `_learnings.md`) **stays tracked** — but for an in-flight ticket the dir lives only on its feature branch; a delivered ticket reaches `main` under `.tickets/completed/<slug>/` via the delivery squash (see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). Only the `.harness/` tree and the two transient `.tickets/` sentinels above are ignored. `.tickets/completed/` is also tracked — delivered tickets are committed to git just like the code that shipped them.

### 4a — Bootstrap the `harness-tickets` coordination branch

Ticket-number allocation and the coarse lifecycle log live on a dedicated orphan `harness-tickets` branch (an append-only `ledger.jsonl`; the design names it `.harness-tickets`, but a git ref may not begin with a dot). Ensure it exists — a no-op when it already does, and it never disturbs the working tree or `main`:

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" ensure-branch --push
```

This creates the orphan branch with an empty ledger and pushes it to `origin` (when a remote exists). If you are adopting the harness on a repo that already has `.tickets/*` and `.tickets/completed/*` from the pre-ledger model, seed the ledger once with `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" migrate --push` (idempotent — it emits a `claim` per existing ticket and a terminal event per completed one, then continues numbering without collision).

### 5 — Write lead-curated stub files

These two files live alongside the tickets and are loaded as context during `/problem` and `/build` so the model respects them from the start. They are **lead-curated**: `_standards.md` is only ever hand-edited, and `_learnings.md` is only appended to by `/deliver` and `/harvest-learnings` **after the lead approves** each entry (append-only, never overwriting). The machine maintains its own separate failure trail in `.harness/memory.db` (BM25-searchable, opaque).

Skip whichever file already exists. Do not overwrite.

#### `.tickets/_standards.md`

```markdown
# Engineering Standards

Project-specific engineering standards. The harness loads this file as context at the start of every `/problem` and `/build`, so the model honors these from the first line of code. Lead-curated — the harness never writes to this file.

Replace each section's bullets with what actually applies to this project. Delete sections that don't apply. Add new sections as needed. Keep entries short — one or two sentences per rule.

The `## Language` and `## Test strategy` sections are required — the harness validator halts `/problem` and `/build` until both are filled with real content.

## Language

- (e.g.) Python 3.12 is the implementation language and runtime; type annotations on every public boundary.

## Code style

- (e.g.) Python: black + ruff, 100-character lines, type annotations on every public boundary.
- (e.g.) Go: gofmt + golangci-lint; no `interface{}` without a written reason on the same line.

## Libraries and frameworks

- (e.g.) HTTP client: `httpx`, not `requests`.
- (e.g.) ORM: SQLAlchemy 2.x `select()` style; legacy `Query` API is forbidden.
- (e.g.) Testing: pytest + pytest-asyncio. Do not use `unittest`.

## Architecture

- (e.g.) Routes are thin: validation + delegation only. Business logic lives under `src/services/`.
- (e.g.) All external IO goes through an adapter; never call third-party APIs from inside business logic.

## Test strategy

- (e.g.) Integration tests hit a real Postgres via testcontainers, never SQLite mocks.
- (e.g.) Behavior coverage is enforced; line coverage is not.

## Documentation

- (e.g.) Public APIs need a docstring with at least one example.
- (e.g.) No comments unless the why is non-obvious; never narrate the what.

## Security

- (e.g.) User input that reaches a subprocess must use an argv list, never a shell string.
- (e.g.) Auth tokens never appear in logs or error responses.

## Post-merge smoke test

Uncomment to have `/deliver` run a smoke test against `main` after the squash-merge. All three are optional; leave them commented to skip the smoke phase entirely.

# smoke_test_command: pytest -q     # run via shlex.split + shell=False, so | > < && ; pass as LITERAL arguments (no pipes/redirects). Trusted, lead-curated value — no allow-list beyond the split. Absent or empty → smoke phase skipped.
# smoke_test_mode: auto-revert      # auto-revert (default): git revert the merge commit on failure, keeping branch + worktree for rework. warn-only: finish delivery but report the failure in the final report.
# smoke_test_timeout: 60            # integer seconds; default 60, max 300 (higher is capped with a warning; non-integer, zero, or negative skips the smoke test with a warning).
```

#### `.tickets/_learnings.md`

Create this by calling `learnings.py` rather than hand-authoring the header text, so this stub and the one `append_learnings()` writes when `_learnings.md` is unexpectedly absent at delivery time can never diverge — both source the same `STUB_HEADER` constant:

```
python3 "${CLAUDE_PLUGIN_ROOT}/learnings.py" stub .tickets/_learnings.md
```

This is idempotent and skip-safe: it writes the stub only if the file does not already exist, matching "skip whichever file already exists. Do not overwrite." above. The written header documents the lead-curated, append-only contract (`/deliver` and `/harvest-learnings` append only after the lead accepts each candidate, via a template-field-only write path — never raw extracted text) and the `<date> | <gate> | <ticket> | <pattern>` format, with worked examples the lead deletes once real entries accumulate.

### 6 — Confirm and orient the user

Report what was created, then:

```
Harness initialized.

Pipeline:
  /problem <description>  → design artifacts → CHECKPOINT 1
  /write-spec XXXX        → specs from solution.md
  /build XXXX             → worktree → implementation → diff
  /deliver XXXX           → merge → clean up

For standalone (no design ceremony):
  /write-spec <description>  → explore codebase → spec
  /build <spec-id>           → temp dir → artifact
  /deliver <run-id>          → write to target file

Lead-curated context (already stubbed under .tickets/):
  _standards.md             ← engineering standards. Edit this first.
  _learnings.md             ← must-fix patterns. Append as the project teaches you things.

Machine-only memory:
  .harness/memory.db        ← BM25-searchable failure trail. Opaque; do not edit.

Edit .harness/config.py to set LANGUAGE if auto-detection is unreliable.
```

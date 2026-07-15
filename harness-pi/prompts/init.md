---
description: Initialize the harness pipeline in the current project.
---
Initialize the harness pipeline in the current project.

## Steps

### 1 — Create harness directory structure

```
.harness/
├── specs/        ← spec files go here
├── tasks/        ← task DAG files go here
├── results/      ← run artifacts go here
├── critiques/    ← /critique reports go here (git-ignored like the rest of .harness/)
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

`.harness/` is machine-local scaffolding and is ignored **wholesale** — so `results/`, `critiques/` (the `/critique` reports), `checkpoints/`, and the `memory.db` failure trail all stay out of git under the same rule; none of them should ever land in a commit. `.tickets/` itself (status.md, problem/requirements/solution.md, NEXT_TICKET, the lead-curated `_standards.md` / `_learnings.md`) **stays tracked** — the harness commits each status transition to `main` (see "Committing ticket metadata" in `/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`). Only the `.harness/` tree and the two transient `.tickets/` sentinels above are ignored. `.tickets/completed/` is also tracked — archived tickets are committed to git just like active ones.

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

```markdown
# Learnings

Must-fix patterns surfaced through gate failures and post-build reviews. The harness loads this file as context at the start of every `/problem` and `/build` so the model avoids repeating the same mistakes. **Lead-curated** — `/deliver` and `/harvest-learnings` append to it, but only after the lead accepts each candidate, and only via a template-field-only write path (they never overwrite existing entries or write raw extracted text). The machine's raw failure trail lives in `.harness/memory.db` (read by `memory(action="retrieve", ...)` before each repair attempt) and is intentionally separate from this file.

Format: one entry per pattern, dated, terse. The `ticket` field is the originating ticket number, or `multi` for a recurring cross-ticket pattern from `/harvest-learnings`.

```
<date> | <gate> | <ticket> | <pattern>
```

Examples (delete these once real entries accumulate):

```
2026-04-12 | type_check | 0031  | Public APIs annotate Optional[X], not X or None — older mypy in CI rejects PEP 604.
2026-04-18 | security   | 0042  | subprocess.run with any user-derived value: argv list + shell=False, no exceptions.
2026-05-02 | test       | multi | Async tests need asyncio_mode = auto in pyproject; without it they silently pass.
```

Add a new line when you encounter a repeated mistake or a pattern worth enforcing. Keep entries terse — the model uses them as guardrails, not documentation. Prune freely; older entries that no longer apply should be removed by hand.
```

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

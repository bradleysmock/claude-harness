Initialize the harness pipeline in the current project.

## Steps

### 1 — Create harness directory structure

```
.harness/
├── specs/        ← spec files go here
├── tasks/        ← task DAG files go here
├── results/      ← run artifacts go here
└── checkpoints/  ← task resume state
.tickets/         ← SDLC ticket directory
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
.worktrees/          # git worktrees
.tickets/.active     # transient active-ticket sentinel
.tickets/.ticket.lock # transient ticket-number claim lock
```

`.tickets/` itself (status.md, problem/requirements/solution.md, NEXT_TICKET, the lead-curated `_standards.md` / `_learnings.md`) **stays tracked** — the harness commits each status transition to `main` (see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). Only the two transient sentinels above are ignored, so they never show as uncommitted noise.

### 5 — Write lead-curated stub files

These two files live alongside the tickets and are loaded as context during `/problem` and `/build` so the model respects them from the start. They are **lead-curated** — the harness never auto-appends to them. The machine maintains its own separate failure trail in `.harness/memory.db` (BM25-searchable, opaque).

Skip whichever file already exists. Do not overwrite.

#### `.tickets/_standards.md`

```markdown
# Engineering Standards

Project-specific engineering standards. The harness loads this file as context at the start of every `/problem` and `/build`, so the model honors these from the first line of code. Lead-curated — the harness never writes to this file.

Replace each section's bullets with what actually applies to this project. Delete sections that don't apply. Add new sections as needed. Keep entries short — one or two sentences per rule.

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

## Testing

- (e.g.) Integration tests hit a real Postgres via testcontainers, never SQLite mocks.
- (e.g.) Behavior coverage is enforced; line coverage is not.

## Documentation

- (e.g.) Public APIs need a docstring with at least one example.
- (e.g.) No comments unless the why is non-obvious; never narrate the what.

## Security

- (e.g.) User input that reaches a subprocess must use an argv list, never a shell string.
- (e.g.) Auth tokens never appear in logs or error responses.
```

#### `.tickets/_learnings.md`

```markdown
# Learnings

Must-fix patterns surfaced through gate failures and post-build reviews. The harness loads this file as context at the start of every `/problem` and `/build` so the model avoids repeating the same mistakes. **Lead-curated** — the harness never appends here. The machine's raw failure trail lives in `.harness/memory.db` (read by `memory(action="retrieve", ...)` before each repair attempt) and is intentionally separate from this file.

Format: one entry per pattern, dated, terse.

```
YYYY-MM-DD | <gate or area> | <one-line pattern>
```

Examples (delete these once real entries accumulate):

```
2026-04-12 | mypy        | Public APIs annotate `Optional[X]`, not `X | None` — older mypy in CI rejects PEP 604.
2026-04-18 | bandit      | `subprocess.run` with any user-derived value: argv list + `shell=False`, no exceptions.
2026-05-02 | pytest      | Async tests need `asyncio_mode = auto` in pyproject; without it they silently pass.
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

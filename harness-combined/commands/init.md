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

### 4 — Add `.worktrees` to `.gitignore`

If `.gitignore` exists, append `.worktrees/` if not already present.
If `.gitignore` does not exist, create it with `.worktrees/`.

### 5 — Confirm and orient the user

Report what was created, then:

```
Harness initialized.

Pipeline:
  /problem <description>  → design artifacts → CHECKPOINT 1
  /write-spec XXXX        → specs from solution.md
  /build XXXX             → worktree → implementation → diff
  /deliver XXXX           → merge → clean up → learnings

For standalone (no design ceremony):
  /write-spec <description>  → explore codebase → spec
  /build <spec-id>           → temp dir → artifact
  /deliver <run-id>          → write to target file

Edit .harness/config.py to set LANGUAGE if auto-detection is unreliable.
```

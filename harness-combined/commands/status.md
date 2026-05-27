Show the current state of all work in the project.

Read `.harness/config.py` if it exists to get PROJECT_ROOT (default: .).

## Steps

### 1 — Ticket status (SDLC workflow)

Scan `.tickets/*/status.md` for open tickets. For each, report: ticket number, title, status.

| Ticket | Title | Status |
|--------|-------|--------|
| XXXX   | ...   | implementing / review-ready / ... |

If there are review-ready tickets, remind the user: run `/gate XXXX` to get gate findings, then `/deliver XXXX` once approved.

### 2 — Spec/build status (standalone workflow)

Call `harness_status(project_root)`.

Format:
- ✓ passed runs — spec-id, timestamp
- ⚠ escalated runs — spec-id, failing gate name, timestamp

If there are passed runs awaiting write-out, remind the user: run `/deliver <run-id>`.
If there are escalated runs, remind the user: run `/debug` to investigate.

### 3 — Failure memory summary

If `.harness/memory.db` exists, note: "Failure memory: N records" (do this with a quick check for the file's existence; don't query the DB).

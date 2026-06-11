# Solution

**Ticket**: 0001
**Title**: Archive Completed and Cancelled Tickets

## Approach

After a ticket transitions to `done` or `cancelled`, move its directory from `.tickets/<XXXX-slug>/`
to `.tickets/completed/<XXXX-slug>/` using an OS-level `mv` (POSIX-atomic for same-volume renames)
followed by `git add`/`git rm` staging. All commands that resolve a ticket by ID search both
locations transparently. A new `/reopen` command moves a ticket back to the active root and sets
`status: solution`. Status/enumeration commands get a distinct "Completed" section.

## Components

| Component | Responsibility |
|-----------|---------------|
| `context/flows/deliver-ticket.md` | Replace Step 6 `git add` with OS mv + `git rm`/`git add -A` archive; archive before commit |
| `commands/cancel.md` | Replace Step 7 commit + Step 8 "preserved" message with: mv archive → commit → Step 9 report |
| `commands/reopen.md` | New command: scan completed/, confirm, mv back, status → `solution`, commit |
| `skills/status/SKILL.md` | Add "Completed Tickets" section below active; scan `.tickets/completed/*/status.md` |
| `commands/ticket-status.md` | Scan both `.tickets/*/status.md` and `.tickets/completed/*/status.md`; show separately |
| `commands/deliver.md` | Ticket ID glob checks `.tickets/<arg>*/` then `.tickets/completed/<arg>*/` |
| `commands/build.md` | Ticket ID glob checks both locations |
| `commands/write-spec.md` | Ticket ID glob checks both locations |
| `commands/gate.md` | Ticket ID glob checks both locations |
| `commands/cancel.md` (ID resolution) | Scan both dirs when resolving ticket ID/slug |
| `commands/requirements.md` | Scan both dirs for ID resolution (needed post-reopen) |
| `commands/solution.md` | Scan both dirs for ID resolution (needed post-reopen) |
| `commands/refine.md` | Scan both dirs for ID resolution (needed post-reopen) |
| `context/flows/build-ticket.md` | Ticket resolution searches both locations |
| `context/flows/write-spec-ticket.md` | Ticket resolution searches both locations |
| `context/harness-reference.md` | Document `.tickets/completed/`, archive lifecycle, reopen status transition |
| `commands/init.md` | Document completed/ subfolder in project layout |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| OS `mv` then `git rm -r`/`git add -A` | `mv` is a single `rename(2)` syscall — truly atomic on POSIX same-volume. `git mv dir/` is NOT atomic: it walks and stages per-file, risking partial-move state. |
| Detect partial-move on startup | If both `.tickets/XXXX-slug/` and `.tickets/completed/XXXX-slug/` exist simultaneously, treat as failed partial archive; root copy is authoritative; warn lead to re-run archive manually. |
| `.tickets/completed/` as single flat folder | Simple, scannable; `status.md` already distinguishes `done` vs `cancelled` |
| `/reopen` status → `solution` | Ensures a lead must re-verify design before `/build`; `solution` is the right re-entry point after a ticket was previously built |
| Only `done` and `cancelled` tickets eligible for reopen | Opening `done` tickets (not just cancelled) is needed when a delivered feature must be revised |

## Status Transition Extension

The following new transition is added to the harness-reference.md status table:

| From | Command | To | Notes |
|------|---------|-----|-------|
| `done` or `cancelled` (in `completed/`) | `/reopen XXXX` | `solution` (back in `.tickets/`) | Lead must re-run `/build XXXX` before work continues |

## Test Plan

| Requirement | Test Type   | Scenario(s)                                                                        |
|-------------|-------------|------------------------------------------------------------------------------------|
| FR-1        | Integration | `/deliver XXXX` completes → `.tickets/XXXX-slug/` absent, `.tickets/completed/XXXX-slug/` present |
| FR-2        | Integration | `/cancel XXXX` completes → ticket archived to completed/                          |
| FR-3        | Unit        | Archive logic rejects ticket with status `implementing` with an error             |
| FR-3 (cancel) | Unit      | Archive logic with `cancelled` status but still at root (simulate Step 7 crash) → archive completes |
| FR-3 (cancel guard) | Unit | Archive logic rejects re-archive when ticket is already in `completed/` and both dirs absent at root |
| FR-4        | Integration | `/reopen XXXX` → `.tickets/completed/XXXX-slug/` absent, `.tickets/XXXX-slug/` present, status = `solution` |
| FR-5        | Integration | `/build XXXX` on archived ticket → command resolves ticket correctly from `completed/` |
| FR-6        | Unit        | Archive when target already exists at `completed/` and root is absent → no error, no change |
| FR-6 (partial) | Unit   | Both root and completed dirs exist → root treated as authoritative; warning emitted |
| FR-7        | Integration | `/deliver` pipeline triggers archive as part of completion; no separate command needed |
| FR-8        | Integration | `/status` shows active tickets in main table; archived tickets in "Completed" section |

## Tradeoffs

- **Chose OS `mv` over `git mv`**: `git mv` is not atomic at the directory level; a crash mid-walk leaves partial-move state with no recovery path. OS rename is atomic. The extra `git rm -r` / `git add -A` staging is slightly more verbose but safe.
- **`/reopen` sets status `solution`**: Forces re-run of `/build`; prevents reopening directly into `implementing` with stale specs.
- **Pre-implementing commands** (`requirements.md`, `solution.md`, `refine.md`, `write-spec.md`) also get dual-scan: needed to support the `/reopen` flow, which returns a ticket to `solution` status and may require the lead to then run these commands.
- **Accepting**: On filesystems where `.tickets/` and `.tickets/completed/` are on different volumes, `mv` is not atomic. This is not a realistic concern for the `.tickets/` directory in a single git repository.

## Risks

- `cancel.md` Step 8 currently says "ticket directory preserved — delete manually." This must be replaced, not appended to, or the lead will see contradictory instructions. Specifically flagged in implementation order.

## Reopen Confirmation Block

```
Ready to reopen ticket XXXX:
  mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/
  status.md → solution
  git add .tickets/XXXX-<slug>/
  git commit -m "chore(ticket): XXXX → solution (reopened)"
Re-run /build XXXX before resuming work. Proceed? (yes/no)
```

If `.tickets/XXXX-<slug>/` already exists at root when `/reopen` is invoked (partial-move-back state), treat the root copy as authoritative, warn the lead, and stop.

## Implementation Order

1. Edit `context/harness-reference.md` — add `completed/` to directory layout; add reopen transition to status table; note that `solution` is now reachable from two paths (forward design and reopen).
2. Edit `context/flows/deliver-ticket.md`:
   - 2a. Replace step 6's `git add .tickets/XXXX-<slug>/` with: write `status: done` to status.md, then `mkdir -p .tickets/completed`, then OS `mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/`, then `git rm -r --cached .tickets/XXXX-<slug>/` (removes old path from index), then `git add -- .tickets/completed/XXXX-<slug>/`, then commit `chore(ticket): XXXX → done`.
   - 2b. Update step 3 confirmation block to add line: `mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/   (archive)`.
3. Edit `commands/cancel.md`:
   - 3a. Update ticket ID resolution (step/line where it says "scan `.tickets/`") to scan both `.tickets/<arg>*/` and `.tickets/completed/<arg>*/`.
   - 3b. After existing Step 7 (status → cancelled commit), insert new Step 8: `mkdir -p .tickets/completed`, OS `mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/`, `git rm -r --cached .tickets/XXXX-<slug>/`, `git add -- .tickets/completed/XXXX-<slug>/`, commit `chore(ticket): XXXX archive → completed/` (separate commit — never amend, as Step 7 commit may have been pushed).
   - 3c. Replace current Step 8 "directory preserved, delete manually" text with Step 9 report that names what was cleaned up.
   - 3d. Update Step 2 confirmation block to include: `mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/   (archive)`.
4. Add `commands/reopen.md` — scan `.tickets/completed/`, validate status is `done` or `cancelled`, show confirmation block (see Reopen Confirmation Block above), OS `mv` back, write status → `solution`, `git add --`, commit `chore(ticket): XXXX → solution (reopened)`.
5. Edit ticket ID resolution in all commands and flow files to check `.tickets/<arg>*/` then `.tickets/completed/<arg>*/` (deliver, build, write-spec, gate, requirements, solution, refine, build-ticket.md, write-spec-ticket.md).
6. Edit `skills/status/SKILL.md` — add "Completed Tickets" section scanning `.tickets/completed/*/status.md`.
7. Edit `commands/ticket-status.md` — scan both dirs; show completed in a separate block.
8. Edit `commands/init.md` — document completed/ subfolder in layout diagram.

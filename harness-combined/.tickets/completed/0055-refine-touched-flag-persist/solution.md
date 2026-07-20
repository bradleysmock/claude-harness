# Solution

**Ticket**: 0055
**Title**: Persist refine-touched flag to disk (Step S writes, Step B checks, deliver clears)

## Approach

Replace the in-session "mark this run refine-touched" note with a durable marker
file `refine-touched.md` in the ticket directory, committed on the branch at S2
**before** `/refine` runs. Every downstream decision point (Step B, deliver,
batch) resolves the marker from the **branch/worktree copy** — the root
`.tickets/` stub never carries it — and `_fold_archive` deletes it inside the
delivery squash. Batch delivery additionally gets a code-level backstop.

## Components

| Component | Change |
|-----------|--------|
| `context/spec-remediation.md` (S2) | Write `refine-touched.md` (date, checks being fixed) into the worktree ticket dir; scoped add + commit on branch **before invoking `/refine`** — write/commit failure ⇒ bail (hard-stop), `/refine` never runs unmarked. Refine commit ref appended after re-score (best-effort; a failed append only thins the audit trail shown at confirmation). |
| `context/flows/autopilot-ticket.md` | Step S: mark = the persisted file. Step B carve-out: `test -f <ticket-dir>/refine-touched.md` against the worktree copy; show file contents as the audit trail. Step B approval is the lead seeing the diff — deliver then proceeds. |
| `context/flows/deliver-ticket.md` | Marker resolved per the Step 1.6 pattern: worktree/branch copy or `git show ticket/XXXX-<slug>:…` — root stub never authoritative. Present ⇒ Step 3 never skipped and prints marker contents. Step 4: documents marker deletion inside the squash. |
| `context/flows/autopilot-batch.md` | Step 0 member resolution probes `git show ticket/XXXX-<slug>:…/refine-touched.md`; marker ⇒ member excluded + reported for interactive delivery. 1 member left ⇒ run `autopilot-ticket.md` on it; 0 left ⇒ stop, all reported. |
| `ticket.py` | `_fold_archive`: `(dst / "refine-touched.md").unlink(missing_ok=True)` after status rewrite, before `git add`. `deliver_squash_batch`: probe **all members up-front** via `git show <member-head>:.tickets/<slug>/refine-touched.md` (zero side effects) and raise `RuntimeError` before the first cherry-pick — batch atomicity preserved for any member position. |
| `tests/test_0055_refine_touched_flag.py` | Unit tests (ticket.py paths) + content-verification tests over the four docs. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Dedicated marker file, not a `status.md` field | Status transitions rewrite `status.md` wholesale; a field is easy to drop silently. File presence is atomic, greppable, `git show`-able on the branch. |
| Visible name `refine-touched.md`, content = audit trail | Step B and deliver Step 3 must show what `/refine` changed; the marker doubles as that artifact. Matches the `gate-findings.md` ticket-dir convention. |
| Write before `/refine`, not after | Closes the mid-S2 crash window; every failure past the write degrades toward confirmation, never auto-delivery. |
| Clear in `_fold_archive`; raise in `deliver_squash_batch` | Single-ticket path has the Step 3 human prompt as second layer; batch has no prompt, so the code seam enforces "a batch member never carries the marker". |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1, FR-2  | Integration | S2 / Step S contain the marker literal, write+commit wording, and the "before invoking `/refine`" ordering phrase. |
| FR-3        | Integration | Step B words the carve-out as an on-disk worktree/branch file check, forbids session memory. |
| FR-4        | Integration | deliver doc: branch-copy resolution wording; Step 3 never skipped while marker present; prints contents. |
| FR-5        | Unit        | `_fold_archive` deletes marker; `deliver_squash` end-to-end → one commit, no marker in tree; no-marker dir byte-identical. |
| FR-6        | Unit        | `deliver_squash_batch` with marker member in any position → raises before first pick; zero new commits, clean tree. |
| FR-7        | Integration | batch doc: Step 0 branch-probe wording, exclusion + both degrade branches (1 left / 0 left) named. |
| FR-8        | Integration | The literal `refine-touched.md` appears in all four docs and `ticket.py`. |

## Tradeoffs

- **Chose a committed marker over gitignored `.harness/` state because**: `.harness/`
  is local scaffolding — lost on worktree removal, invisible to resumed sessions.
- **Accepting**: double confirmation when Step B approves and a direct `/deliver`
  follows later (belt-and-suspenders, fail-closed direction); and the archived
  `completed/` dir losing the marker as post-delivery audit trail — the lead saw
  it at confirmation time.

## Risks

- Flow docs are shared-conflict hotspots under concurrent deliveries — mitigate
  with soft-squash + rebase-onto-main chase at delivery time.
- Existing `ticket.py` tests may pin `_fold_archive`/batch staging sequence — run
  them first; widen fakes only where the assertion is incidental.

## Implementation Order

1. Tests first: `tests/test_0055_refine_touched_flag.py` (unit + content checks).
2. `ticket.py`: `_fold_archive` deletion (FR-5) + batch raise guard (FR-6).
3. `context/spec-remediation.md` S2 write-before-refine (FR-1).
4. `context/flows/autopilot-ticket.md` Step S + Step B (FR-2, FR-3).
5. `context/flows/deliver-ticket.md` branch-copy resolution + Step 3/4 (FR-4, FR-5).
6. `context/flows/autopilot-batch.md` Step 0 exclusion + degrade (FR-7).

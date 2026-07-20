# Requirements

**Ticket**: 0055
**Title**: Persist refine-touched flag to disk (Step S writes, Step B checks, deliver clears)

## Functional Requirements

1. `context/spec-remediation.md` S2 must write a marker file `refine-touched.md`
   (date, the semantic checks being fixed) into the worktree ticket directory and
   commit it on the branch **before invoking `/refine`**; if the write or commit
   fails, S2 must bail (hard-stop) rather than invoke `/refine` — machine-adjusted
   scope must never exist on the branch without a committed marker. Appending the
   refine commit ref in a follow-up commit after the re-score is optional.
2. `context/flows/autopilot-ticket.md` Step S must describe the mark as the
   persisted marker file, not an in-session note.
3. `context/flows/autopilot-ticket.md` Step B must decide the carve-out by
   checking for `refine-touched.md` on disk in the **worktree/branch** ticket
   directory — never session memory — and show its contents as the `/refine`
   audit trail.
4. `context/flows/deliver-ticket.md` must resolve the marker from the branch's
   copy (worktree path or `git show ticket/XXXX-<slug>:…`), never the root
   `.tickets/` stub (per the existing Step 1.6 / Ticket-resolution pattern). When
   present, the Step 3 confirmation must not be skipped — autopilot's skip-Step-3
   override does not apply — and the confirmation block prints the marker contents.
5. `ticket.py` `_fold_archive` must delete `refine-touched.md` from the archived
   ticket directory (when present) before staging, clearing the flag inside the
   one squash commit; `context/flows/deliver-ticket.md` Step 4 must document it.
6. `ticket.py` `deliver_squash_batch` must probe every member **before the first
   cherry-pick** (`git show <member-head>:.tickets/<slug>/refine-touched.md`) and
   raise if any carries the marker — before any commit or index state is touched,
   preserving batch atomicity regardless of the member's position.
7. `context/flows/autopilot-batch.md` must exclude marker-carrying members at
   Step 0 member resolution, probing the **branch** copy
   (`git show ticket/XXXX-<slug>:…/refine-touched.md`); excluded members are
   reported for interactive delivery. Exactly 1 member remaining → run
   single-ticket autopilot on it; 0 remaining → stop, all members reported.
8. The marker filename must be the single literal `refine-touched.md` everywhere.

## Non-Functional Requirements

1. Fail-closed: loss of session context at any point — including mid-S2 — must
   never re-enable auto-delivery of a refine-touched ticket.
2. The one-commit-per-delivery invariant of `deliver_squash` is preserved.
3. Touched Python passes the gate's exact lint/type checks (no new findings).

## Test Strategy

| Type        | Rationale                                                        |
|-------------|------------------------------------------------------------------|
| Unit        | `_fold_archive` marker deletion; `deliver_squash` one-commit + clean tree; `deliver_squash_batch` raises up-front for a marker member in **any position** — zero new commits, clean tree; no-marker paths unchanged. |
| Integration | Content-verification tests assert the marker literal, the branch-copy check-location wording (FR-3/4/7), and the "before invoking `/refine`" ordering phrase (FR-1) in all four docs. |

## Acceptance Criteria

- `deliver_squash` over a ticket dir with the marker → `completed/` dir without
  it, exactly one commit; without the marker → byte-identical to today.
- `deliver_squash_batch` with a marker member in any position → raises before the
  first pick; zero new commits, clean tree.
- All four docs contain the literal `refine-touched.md`; Step B / deliver / batch
  checks are worded against the branch/worktree copy; existing tests still pass.

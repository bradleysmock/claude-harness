---
name: review
description: Review a ticket's implementation against its problem/requirements/solution before merge. TRIGGER when the user asks to review a ticket, check a worktree's diff before /deliver, assess whether a ticket is merge-ready, or invoke the post-build critic on a specific ticket (e.g. "review ticket 0003", "look at the diff on 0007 before I deliver", "is ticket 0012 ready to merge?"). SKIP for general code review of arbitrary diffs unrelated to a ticket (use the critique skill instead), for ad-hoc style/lint checks (use /gate), and during active /build sessions on the same ticket (wait for /build to finish).
---

# Review skill — ticket-scoped post-build review

Conduct a code review for a ticket whose `/build` has completed. The lead invokes this between `/build` and `/deliver`. Findings are reported directly without a critic loop; the lead decides what to act on.

## Ticket resolution

If the user named a ticket number, use it. Otherwise scan `.tickets/` for tickets with `status: review-ready`. If exactly one exists, use it; if multiple exist, list them and require the lead to specify before continuing.

## Steps

0. **Guard against concurrent automated sessions.** If `.tickets/.active` exists and contains this ticket's slug, an automated `/build` session may be in progress. Warn the lead and recommend waiting before proceeding. Do not stop — proceed if the lead confirms.

1. Read `problem.md`, `requirements.md`, and `solution.md` as the review baseline.

2. Derive the worktree path from `status.md` (read the `branch` field, strip the `ticket/` prefix, resolve `.worktrees/XXXX-<slug>` relative to project root). Read all implementation code and tests in that directory.

3. Evaluate the implementation across these dimensions:

   **Requirements coverage**
   - Does each functional requirement have a corresponding test and passing implementation?
   - Are all acceptance criteria met?

   **Test quality**
   - Are tests testing behavior, not implementation details?
   - Are edge cases and failure modes covered?
   - Are tests isolated and deterministic?
   - Is coverage meaningful (not line-coverage theater)?

   **Security**
   - Are there injection vulnerabilities (SQL, command, template)?
   - Is user input validated at boundaries?
   - Are secrets handled safely (not hardcoded, not logged)?
   - Are dependencies pinned or from trusted sources?

   **Correctness**
   - Off-by-one errors, race conditions, unhandled nulls?
   - Are errors surfaced and handled appropriately?

   **Clarity and maintainability**
   - Is the code understandable without excessive comments?
   - Are names accurate and descriptive?
   - Is there dead code or unnecessary complexity?

   **Alignment with solution**
   - Does the implementation match the agreed architecture and tech choices?
   - Were significant deviations made? If so, are they justified?

4. Present structured findings using these tiers:

   **Must-fix** (blocks merge)
   - `<file:line>` — `<description>`

   **Should-fix** (fix now unless effort is large)
   - `<file:line>` — `<description>`

   **Suggestion** (optional, future consideration)
   - `<brief note>`

   Omit a tier if it has no items.

5. **If approved** (no must-fix items):
   - Keep `status.md` at `review-ready`.
   - Tell the lead the ticket is approved and they can run `/deliver XXXX`.

6. **If changes required** (must-fix items exist):
   - Update `status.md` to `status: changes-requested`.
   - List which items need addressing.
   - Tell the lead to invoke `/build XXXX` to continue work in the existing worktree.

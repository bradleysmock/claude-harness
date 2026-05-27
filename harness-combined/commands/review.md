Conduct a code review for a ticket. Manual path — the automated `/build` flow runs review via a critic agent. When run manually, findings are reported directly without a critic loop.

## Ticket Resolution

If a ticket number is provided as an argument, use it. Otherwise scan `.tickets/` for tickets with `status: review-ready`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

0. **Guard against concurrent automated sessions.** Check whether `.tickets/.active` exists and contains this ticket's slug. If it does, warn the lead that an automated `/build` session appears to be in progress for this ticket and recommend waiting for it to finish before running a manual review. Do not stop — proceed if the lead confirms.

1. Read `problem.md`, `requirements.md`, and `solution.md` as the review baseline.

2. Derive the worktree path from `status.md`: read the `branch` field (e.g. `ticket/XXXX-<slug>`), strip the `ticket/` prefix, and resolve `.worktrees/XXXX-<slug>` relative to the project root. Read all implementation code and tests in that directory.

3. Evaluate the implementation across these dimensions:

   **Requirements coverage**
   - Does each functional requirement have a corresponding test and passing implementation?
   - Are all acceptance criteria met?

   **Test quality**
   - Are tests testing behavior, not implementation details?
   - Are edge cases and failure modes covered?
   - Are tests isolated and deterministic?
   - Is coverage meaningful (not just line coverage theater)?

   **Security**
   - Are there injection vulnerabilities (SQL, command, template)?
   - Is user input validated at boundaries?
   - Are secrets handled safely (not hardcoded, not logged)?
   - Are dependencies pinned or from trusted sources?

   **Correctness**
   - Are there off-by-one errors, race conditions, or unhandled nulls?
   - Are errors surfaced and handled appropriately?

   **Clarity and maintainability**
   - Is the code understandable without excessive comments?
   - Are names accurate and descriptive?
   - Is there dead code or unnecessary complexity?

   **Alignment with solution**
   - Does the implementation match the agreed architecture and tech choices?
   - Were any significant deviations made? If so, are they justified?

4. Present structured findings using these tiers:

   **Must-fix** (blocks merge)
   - <item>: <file path:line and description>

   **Should-fix** (fix now unless large effort — if large, open a ticket)
   - <item>: <file path:line and description>

   **Suggestion** (optional, future consideration — not actioned)
   - <item>: <brief note>

   Omit a tier if it has no items.

5. **If approved** (no must-fix items):
   - Update `status.md` to `status: review-ready`
   - Tell the lead the ticket is approved and they can run `/deliver XXXX`.

6. **If changes required** (must-fix items exist):
   - Update `status.md` to `status: changes-requested`
   - Note which items need to be addressed
   - Lead can invoke `/build XXXX` to continue work in the existing worktree

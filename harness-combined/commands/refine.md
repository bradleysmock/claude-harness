Iterate on the solution design before implementation. Manual escape hatch for additional refinement passes.

> When this overwrites an existing ticket artifact, the `pre_ticket_diff` hook automatically prints a unified diff of the pending change before the write (set `HARNESS_NO_DIFF=1` to suppress).

The default (below) is the **interactive** mode the lead invokes. Autopilot's
Step S calls `/refine` in a distinct **non-interactive** mode — see "Autopilot
(non-interactive) mode" at the end; that mode suppresses every interactive step
here.

## Ticket Resolution

If a ticket number is provided as an argument, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found. Otherwise scan `.tickets/` for tickets with `status: solution`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. Read `problem.md`, `requirements.md`, and `solution.md` in full.

2. Proactively surface anything that could cause problems in implementation:
   - Ambiguous requirements the solution doesn't fully address
   - **FRs flagged by score-spec's `FR testability` check (WARN)** — requirements from
     which no failing test is derivable (no concrete actor/action/observable outcome);
     tighten each into a testable statement
   - Edge cases not covered in the test plan
   - Implementation details not yet decided (data schemas, API contracts, error handling)
   - Missing test scenarios
   - Dependencies or sequencing risks in the implementation order

3. For each item, propose specific options with tradeoffs rather than asking open-ended questions.

4. After each resolved item, update `solution.md` to reflect the decision. Track unresolved items in an Open Questions section.

5. Status stays at `solution` — `/refine` can be run multiple times. If you revised `solution.md` (or any artifact), commit the change **inside the worktree on the branch** so it is not left local-only and never lands on `main` (the artifacts live on the branch per the **Ticket resolution** rule in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`; scoped add — see "Committing ticket metadata" there):

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX refine solution"
```

If no artifact was changed this pass, skip the commit.

6. When satisfied, suggest `/write-spec XXXX` to formalize the solution into specs, then `/build XXXX` to begin implementation.

## Autopilot (non-interactive) mode

Entered **only** when invoked by `autopilot-ticket.md` Step S (see
`${CLAUDE_PLUGIN_ROOT}/context/spec-remediation.md`) to clear a *semantic*
score-spec BLOCK (`FR count`, `No placeholders`) that the mechanical fixers cannot
touch. This mode replaces the interactive Steps above, not augments them.

Rules:

1. **Single pass.** Make at most one revision pass — no iterate-until-satisfied loop.
2. **Fix only the flagged checks.** Address exactly the score-spec checks Step S
   passes in (e.g. the specific placeholder spans, or the missing FR for an
   `FR count` BLOCK). Do not refactor, re-scope, or "improve" anything else.
3. **Derive from existing text only.** Resolve each check using content already
   present in `problem.md` / `requirements.md` / `solution.md`. For an `FR count`
   BLOCK, an FR may be promoted only if it is already implied by existing artifact
   text — **never invent net-new scope**. For a placeholder, replace the marker
   with the concrete value the surrounding text already determines.
4. **No prompts, no Open Questions.** Surface no clarifying questions, no Open
   Questions section, and no next-command suggestions (skip the interactive Step 2,
   Step 3, and Step 6 behaviors entirely). This mode runs unattended.
5. **Bail if undrivable.** If a flagged check cannot be resolved from existing text
   without fabricating scope (e.g. `FR count` is short and no further FR is implied),
   make no change and report **bail** to Step S. Do not guess.
6. **Commit on change.** If an artifact was revised, commit it **on the branch inside
   the worktree** exactly as in Step 5 (`chore(ticket): XXXX refine solution`) — never
   to `main`. Step S re-scores the committed worktree files. If nothing changed (bail),
   make no commit.


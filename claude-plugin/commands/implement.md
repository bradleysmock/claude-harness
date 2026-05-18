Autonomous TDD implementation in a worktree, followed by gate checks and a critic/review loop. Stops at checkpoint 2 for lead approval to merge.

If `.tickets/_learnings.md` exists, load it via @.tickets/_learnings.md.
If `.tickets/_conventions.md` exists, load it via @.tickets/_conventions.md.

## Ticket Resolution

A ticket number argument is required. If none is provided, scan `.tickets/` for tickets with `status: solution` or `status: changes-requested`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

---

## Pre-flight

1. Read `problem.md`, `requirements.md`, and `solution.md` for the resolved ticket. If there are unresolved open questions that block implementation, raise them before proceeding.

---

## Setup

All main-repo git operations must complete before any subagent is spawned. Do not proceed to the TDD cycle until git setup is confirmed.

2. Create the branch:
   ```
   git branch ticket/XXXX-<slug>
   ```

3. Create the worktree:
   ```
   mkdir -p .worktrees
   git worktree add .worktrees/XXXX-<slug> ticket/XXXX-<slug>
   ```

4. Confirm the worktree directory exists at `.worktrees/XXXX-<slug>`. If either git command failed (e.g. index lock contention), stop and report the error — do not attempt to continue with a broken worktree.

5. Update `status.md` to `status: implementing`.

6. Write the active-ticket sentinel so the stop hook gates only this session's worktree:
   ```
   echo 'XXXX-<slug>' > .tickets/.active
   ```
   This prevents the stop hook from running gates on other review-ready tickets that belong to a different session.

---

## TDD Cycle

For each item in the Implementation Order from `solution.md`:

### Step A — Write failing tests

Based on the Test Plan in `solution.md`, write the tests for the current requirement before writing any implementation code. Tests should:
- Cover the happy path
- Cover documented edge cases and failure modes
- Use the test types specified in the test plan (unit, contract, UI, integration)
- Be named clearly so the intent is obvious

### Step B — Implement to pass

Write the minimum implementation code needed to make the tests pass. Do not over-engineer. Do not add features not covered by the current tests.

### Step C — Refactor

If the code can be made clearer or more maintainable without changing behavior, do so now. Run tests after refactoring to confirm they still pass.

Repeat A → B → C for each requirement.

---

## Gate / Critic / Review Loop

When all requirements have passing tests:

1. Run the full test suite and confirm everything passes.

2. Commit all work in the worktree using the appropriate conventional commit type (`feat:`, `fix:`, `refactor:`, `test:`, `chore:`, etc.):
   ```
   git -C .worktrees/XXXX-<slug> add .
   git -C .worktrees/XXXX-<slug> commit -m "<type>: <short description>"
   ```
   Confirm the commit succeeds and `git status` shows a clean tree before continuing.

3. Update `status.md` to `status: review-ready`.

4. **Run `/gate XXXX`** to execute lint, type-check, SAST, and the full pytest suite against the worktree. Results are written to `.tickets/XXXX-<slug>/gate-findings.md`. Address any failures, commit fixes, and re-run `/gate XXXX` until the report is clean. The critic should not see issues the gates can already catch.

5. UI smoke (conditional). If `git -C .worktrees/XXXX-<slug> diff --name-only main | grep -E 'templates/|routes/|static/'` is non-empty, start the dev server in the worktree, exercise the changed flow end-to-end in a browser, and capture a one-paragraph observation (URL hit, expected response, any errors) for the Checkpoint 2 summary. If you cannot run a browser, say so explicitly — do not silently skip.

6. Verify that all artifact files and the implementation exist and are non-empty before spawning the critic:
   - `.tickets/XXXX-<slug>/problem.md`
   - `.tickets/XXXX-<slug>/requirements.md`
   - `.tickets/XXXX-<slug>/solution.md`
   - `.tickets/XXXX-<slug>/gate-findings.md`
   - Source and test files in `.worktrees/XXXX-<slug>/`

7. Spawn the **critic subagent** (`subagent_type: critic`) with this brief:

   > Phase: **code**
   > Ticket: **XXXX-<slug>**
   > Round: **1** (max 2)
   >
   > Follow `@${CLAUDE_PLUGIN_ROOT}/context/critic-brief.md`. Read `.tickets/XXXX-<slug>/gate-findings.md` before reviewing — do not re-flag what the gates already covered. Focus on dimensions gates cannot cover: abstraction, naming, domain modeling, McGraw design-level flaws, panel-specific issues. Read all source and test files in `.worktrees/XXXX-<slug>/` before producing any finding.

8. For each finding from the critic:
   - **Must-fix**: fix it, re-run the full test suite, confirm passing.
   - **Should-fix**: fix it if the effort is contained. If it is a large effort, open a new ticket using the standard NEXT_TICKET lock mechanism in `.tickets/`, and note it as deferred.
   - **Suggestion**: log it in the checkpoint 2 summary only — do not act on it.

9. If any fixes were made, commit again, then re-run `/gate XXXX` to confirm gates still pass:
   ```
   git -C .worktrees/XXXX-<slug> add .
   git -C .worktrees/XXXX-<slug> commit -m "fix: address critic findings"
   ```
   If the critic produced any Must-fix items in Round 1, spawn a second critic round (`Round: 2`) to review the fixes. **Maximum 2 rounds.**

---

## Checkpoint 2 — Present to Lead

Present a concise summary and wait for approval:

```
## Checkpoint 2: Ready to merge?

**Ticket**: XXXX — <title>

### Implementation summary
<2–3 bullets: what was built, test count, all passing>

### Review findings
- Must-fix: <count and what was fixed, or "none">
- Should-fix: <fixed items + any deferred ticket numbers, or "none">
- Suggestions: <brief list, or "none">

### Deferred tickets
<Ticket numbers and titles for any large should-fix items. Empty if none.>

---
Approve to merge? (yes / no / feedback)
```

Do not merge until the lead approves. Run `/merge XXXX` once approved.

**Do not push unless the lead asks.**

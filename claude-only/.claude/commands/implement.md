Autonomous TDD implementation in a worktree, followed by a critic/review loop. Stops at checkpoint 2 for lead approval to merge.

## Ticket Resolution

A ticket number argument is required. If none is provided, scan `.tickets/` for tickets with `status: solution`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

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

## Critic/Review Loop

When all requirements have passing tests:

1. Run the full test suite and confirm everything passes.

2. Commit all work in the worktree:
   ```
   git -C .worktrees/XXXX-<slug> add .
   git -C .worktrees/XXXX-<slug> commit -m "feat: <short description>"
   ```
   Confirm the commit succeeds and `git status` shows a clean tree before continuing.

3. Update `status.md` to `status: review-ready`.

4. Verify that all artifact files and the implementation exist and are non-empty before spawning the critic:
   - `.tickets/XXXX-<slug>/problem.md`
   - `.tickets/XXXX-<slug>/requirements.md`
   - `.tickets/XXXX-<slug>/solution.md`
   - Source and test files in `.worktrees/XXXX-<slug>/`

5. Spawn a **critic agent** (isolated full Agent invocation) with this brief:

   > You are a senior engineer conducting a code review. You are **read-only** — do not create, modify, or delete any files.
   >
   > ## Step 1: Determine and load active panels
   >
   > Examine the files in `.worktrees/XXXX-<slug>/`. Always read `.claude/panels/core.md`. Then load additional panels based on what's in scope:
   > - `*.py` files or test files → `.claude/panels/python.md`
   > - Route handlers → `.claude/panels/http-api.md`
   > - Templates or static assets → `.claude/panels/ui.md`
   > - LLM client code → `.claude/panels/ai-llm.md`
   >
   > Announce which panels are active.
   >
   > ## Step 2: Read all files
   >
   > - `.tickets/XXXX-<slug>/problem.md`
   > - `.tickets/XXXX-<slug>/requirements.md`
   > - `.tickets/XXXX-<slug>/solution.md`
   > - All source and test files in `.worktrees/XXXX-<slug>/`
   >
   > ## Step 3: Produce findings
   >
   > Read all files before writing a single finding. Apply every dimension from the loaded panel files. Use these severity tiers:
   > - **Must-fix** (blocks merge): correctness bugs, security vulnerabilities, requirements not covered by tests
   > - **Should-fix** (fix now unless large effort): test quality gaps, clarity issues, unnecessary complexity
   > - **Suggestion** (optional, future): architectural improvements, nice-to-haves
   >
   > Include file paths and line numbers for all findings. Return findings as structured text.

6. For each finding from the critic:
   - **Must-fix**: fix it, re-run the full test suite, confirm passing.
   - **Should-fix**: fix it if the effort is contained. If it is a large effort, open a new ticket using the standard NEXT_TICKET lock mechanism in `.tickets/`, and note it as deferred.
   - **Suggestion**: log it in the checkpoint 2 summary only — do not act on it.

7. If any fixes were made, commit again:
   ```
   git -C .worktrees/XXXX-<slug> add .
   git -C .worktrees/XXXX-<slug> commit -m "fix: address review findings"
   ```

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

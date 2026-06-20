# Eval Fixture — suggest skill

Fixed-state baseline for verifying suggestion quality and deduplication behavior.

---

## Fixture State

### Commands (2)

- `build`
- `deliver`

### Skills (1)

- `review`

### Open Tickets (2)

| Ticket | Title |
|--------|-------|
| 0001   | Parallel gate execution |
| 0002   | Auto-cancel stale branches |

---

## Expected Behavior

When the suggest skill runs against this fixture state, it must:

1. **Surface ≥5 non-trivial suggestions** where:
   - **Non-trivial**: names a specific new command, skill, flow, or integration not present in the fixture's `build` / `deliver` / `review` inventory
   - **Trivial** (excluded): names something already in the commands/skills list (e.g. "add a build command", "add a review skill")

2. **Deduplicate correctly**: no suggestion may cover topics that duplicate either open ticket
   - Excluded topics: parallelism / concurrency / gate performance (from "Parallel gate execution")
   - Excluded topics: branch cleanup / stale branch removal / branch lifecycle (from "Auto-cancel stale branches")

3. **Format each row correctly**: title, one-sentence description, effort label (small / medium / large)

---

## How to Run

The suggest skill reads the live filesystem. To test against the fixture state rather than the real harness, follow these steps:

1. Create a temp directory with the fixture layout:

   ```
   mkdir -p /tmp/suggest-fixture/commands /tmp/suggest-fixture/skills/review /tmp/suggest-fixture/.tickets/0001-parallel/  /tmp/suggest-fixture/.tickets/0002-stale/
   touch /tmp/suggest-fixture/commands/build.md
   touch /tmp/suggest-fixture/commands/deliver.md
   printf 'status: implementing\ntitle: Parallel gate execution\n' > /tmp/suggest-fixture/.tickets/0001-parallel/status.md
   printf 'status: implementing\ntitle: Auto-cancel stale branches\n' > /tmp/suggest-fixture/.tickets/0002-stale/status.md
   ```

2. Invoke the suggest skill and instruct it to read from `/tmp/suggest-fixture/` as the project root in place of the current working directory.

3. Verify each item in the **Expected Behavior** checklist against the output.

If running in the real harness is unavoidable, override Step 1 of the skill by providing the fixture inventory manually ("treat the current harness as if it has only the commands: build, deliver and skills: review") and verify deduplication behavior only.

---

## Example Passing Suggestions (for calibration)

The following would all count as non-trivial and non-duplicate against the fixture:

| # | Title | Description | Effort |
|---|-------|-------------|--------|
| 1 | Changelog generation | Auto-generate a CHANGELOG.md from commit history and delivered tickets on `/deliver`. | small |
| 2 | Dependency update skill | Surface outdated dependencies by running `pip list --outdated` / `npm outdated` and formatting results as a ticket-ready report. | medium |
| 3 | Rollback command | Reverse a delivered ticket: undo the merge, restore the worktree, and reset status to review-ready. | large |
| 4 | Ticket export | Export open tickets to a portable JSON/CSV format for syncing to external issue trackers (Linear, GitHub Issues). | medium |
| 5 | Pre-commit hook install | Add a `/hooks-install` command that writes a `.git/hooks/pre-commit` script running the full gate suite locally before each commit. | small |

### Would-be Excluded Suggestions (deduplication calibration)

The following would be **correctly filtered out** against this fixture:

| Title | Reason excluded |
|-------|----------------|
| Parallel build jobs | Duplicates "Parallel gate execution" — covers parallelism/concurrency topic |
| Auto-expire branches | Duplicates "Auto-cancel stale branches" — covers branch lifecycle topic |
| Add a build command | Trivial — `build` is already in the fixture commands inventory |

---

## Failure Cases

A run against this fixture **fails** if:

- Fewer than 5 suggestions are produced
- Any suggestion names a capability already in the fixture inventory (`build`, `deliver`, `review`)
- Any suggestion covers parallelism/concurrency or branch lifecycle topics (duplicate of open tickets)
- Any row is missing title, description, or effort
- Any accepted-suggestion output line exceeds 120 characters

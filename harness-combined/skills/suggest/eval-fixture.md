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

## Example Passing Suggestions (for calibration)

The following would all count as non-trivial and non-duplicate against the fixture:

| # | Title | Description | Effort |
|---|-------|-------------|--------|
| 1 | Changelog generation | Auto-generate a CHANGELOG.md from commit history and delivered tickets on `/deliver`. | small |
| 2 | Dependency update skill | Surface outdated dependencies by running `pip list --outdated` / `npm outdated` and formatting results as a ticket-ready report. | medium |
| 3 | Rollback command | Reverse a delivered ticket: undo the merge, restore the worktree, and reset status to review-ready. | large |
| 4 | Ticket export | Export open tickets to a portable JSON/CSV format for syncing to external issue trackers (Linear, GitHub Issues). | medium |
| 5 | Pre-commit hook install | Add a `/hooks-install` command that writes a `.git/hooks/pre-commit` script running the full gate suite locally before each commit. | small |

---

## Failure Cases

A run against this fixture **fails** if:

- Fewer than 5 suggestions are produced
- Any suggestion names a capability already in the fixture inventory (`build`, `deliver`, `review`)
- Any suggestion covers parallelism/concurrency or branch lifecycle topics (duplicate of open tickets)
- Any row is missing title, description, or effort
- Any accepted-suggestion output line exceeds 120 characters

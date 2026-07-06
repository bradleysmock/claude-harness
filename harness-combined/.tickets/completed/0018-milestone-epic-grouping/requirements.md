# Requirements

**Ticket**: 0018
**Title**: Milestone and Epic Grouping

## Functional Requirements

1. The system must support a `.tickets/_milestones.md` file that defines named milestones; each milestone entry contains at minimum a name and an optional description.
2. The system must support a `milestone:` field in each ticket's `status.md`; if present, the ticket is associated with the named milestone.
3. A ticket must belong to at most one milestone; if multiple `milestone:` fields are present the first value is used.
4. The system must provide a `/milestone` command that lists all milestones defined in `_milestones.md` with: completion percentage, count of done tickets, count of remaining tickets, and estimated remaining effort (sum of `effort` for non-done tickets).
5. The `/milestone` command must accept an optional `<name>` argument to show detail for a single milestone including its ticket list (ticket #, title, status, effort).
6. `/ticket-list` must support a `--milestone <name>` filter flag that shows only tickets tagged to that milestone.
7. Tickets with no `milestone:` field are excluded from all milestone views but still appear in unfiltered `/ticket-list` output.
8. If `_milestones.md` does not exist, `/milestone` must print an informative message ("No milestones defined. Create `.tickets/_milestones.md` to get started.") rather than crashing.
9. If `--milestone <name>` is passed to `/ticket-list` and no tickets match, the system must print "No tickets found for milestone '<name>'." rather than silent empty output.
10. Effort rollup for estimated remaining effort must treat missing `effort` fields as zero and display a warning count ("N tickets have no effort estimate").
11. Completion percentage is computed as `done_count / total_count * 100`; if a milestone has zero tickets the percentage is `0%` and a note "no tickets assigned" is shown.
12. `/milestone` must sort milestones alphabetically by name in the summary view.

## Non-Functional Requirements

1. `/milestone` must complete in under 3 seconds on a `.tickets/` directory with up to 200 tickets across 20 milestones.
2. `/milestone` output must be readable in an 80-column terminal without wrapping milestone names or percentages.
3. Long milestone names (>30 chars) must be truncated with `…` in the summary table to maintain alignment.

## Tech Stack

Both `/milestone` and the `/ticket-list --milestone` extension are Claude Code slash commands implemented as markdown prompt files. They instruct Claude to execute bash to collect and aggregate data. No new runtime dependency is introduced. `_milestones.md` uses a simple YAML front-matter or fenced-block format consistent with other harness markdown files.

## Test Strategy

| Type        | Rationale                                                                      |
|-------------|--------------------------------------------------------------------------------|
| Unit        | Field parsing for `milestone:` in status.md; effort rollup with missing fields |
| Integration | Fixture `.tickets/` with `_milestones.md` and tagged tickets; assert all views  |

## Acceptance Criteria

- `/milestone` with no args prints a table of all milestones: name, completion %, done count, remaining count, estimated remaining effort.
- `/milestone v2.0` prints the detail view for the "v2.0" milestone with its ticket list.
- `/ticket-list --milestone v2.0` shows only tickets where `milestone: v2.0`.
- A ticket with no `milestone:` field does not appear in any `/milestone` output.
- A ticket with `milestone: v2.0` appears in `/milestone v2.0` detail and in `/ticket-list --milestone v2.0`.
- Completion percentage is `0%` for a milestone with no tickets; `100%` when all tickets are done.
- Missing `effort` fields are treated as zero and a warning is printed noting the count.
- Running `/milestone` when `_milestones.md` does not exist prints the setup message without error.
- A milestone referenced in a ticket's `status.md` but absent from `_milestones.md` is shown with a "(undefined)" annotation in `/ticket-list --milestone` output.

## Open Questions

- Should `_milestones.md` use a YAML front-matter format or a simple markdown list? The YAML approach is consistent with `status.md` key-value fields and easier to parse with `grep`; a markdown list is more human-readable. Recommend YAML-like sections (one `## Milestone Name` heading per milestone) for readability, with description in the body.
- Should `/milestone` command live at `commands/milestone.md` (new file) or extend `commands/ticket-list.md`? Separate file preferred for clarity and independent evolution.

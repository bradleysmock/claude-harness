# Solution

**Ticket**: 0018
**Title**: Milestone and Epic Grouping

## Approach

Add `milestone:` and `effort:` optional fields to the `status.md` template in `commands/problem.md`. Define milestones in `.tickets/_milestones.md` using a `## milestone: Name` heading format (discriminating prefix prevents spurious matches on explanatory headings). Implement `/milestone` as a new command file (`commands/milestone.md`) that reads `_milestones.md` and all `status.md` files in a single-pass collection (one `cat` per file, not per-field grep), aggregates per-milestone stats, and renders a summary table or detail view. Extend `commands/ticket-list.md` (ticket 0007 deliverable — must be complete before step 6) with `--milestone <name>` filter support. All milestone name values are validated against `[A-Za-z0-9._-]` (max 40 chars) at parse time; out-of-range values are flagged as "(invalid-name)".

## Dependency

**This ticket depends on 0007 (`ticket-list-command`).**
- Step 1 (template edit to `commands/problem.md`) overlaps with 0007 step 1 (`effort:` field). If 0007 is merged first, only add `milestone:` in step 1 here.
- Step 6 (`--milestone` filter in `commands/ticket-list.md`) cannot be implemented until `commands/ticket-list.md` exists (0007 deliverable). Coordinate branch or implement after 0007 merges.

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `commands/milestone.md` | New slash command; orchestrates bash collection, aggregation, and rendering | Claude executes bash as instructed |
| `commands/ticket-list.md` (edit) | Add `--milestone <name>` filter flag | Reads `milestone:` field from `status.md` |
| `commands/problem.md` (edit) | Add `milestone:` and `effort:` optional fields to `status.md` template | Template update only |
| `.tickets/_milestones.md` (new, lead-managed) | Defines named milestones; `## milestone: Name` heading + optional description | Read by `/milestone` command |
| Bash collection step | Reads each `status.md` once (`cat`); extracts all fields in one pass; validates milestone name charset | Emits per-ticket records as tab-separated lines |
| Name validator | Checks milestone names against `[A-Za-z0-9._-]` max 40 chars; flags "(invalid-name)" | Applied to both file-extracted values AND CLI `<name>` arguments before any comparison, bash expansion, or display |
| `_milestones.md` parser | Greps `^## milestone: ` prefix; validates for duplicate headings (warn to stderr: `>&2 echo "[WARN] duplicate: '$name'"`); skips blank names | Emits milestone name list; warnings on stderr do not contaminate stdout table |
| Aggregation logic | Groups validated records by milestone name; computes done count (`status=done`), total, remaining effort sum (non-done tickets only) | Drives rendering |
| Table/detail renderer | Summary table (name, %, done, remaining, effort pts labeled); detail ticket list | Claude renders inline |

## Tech Choices

| Choice | Rationale |
|---|---|
| Markdown command file (not a skill) | Consistent with `/ticket-status` and `/ticket-list` patterns; no new infrastructure |
| `## milestone: Name` discriminating prefix | Prevents operator explanatory headings (`## Notes`, `## About`) from being parsed as milestone names (D-09) |
| Single-pass `cat` per status.md | Reads each file once instead of one `grep` subprocess per field; reduces ~600 process spawns to ~200 at 200 tickets (D-07) |
| Milestone name validation (`[A-Za-z0-9._-]`, max 40) | Prevents shell metacharacter injection from file-extracted values entering bash pipelines unquoted (D-01); applied before any comparison or display |
| `_milestones.md` duplicate-heading check | Parser emits operator warning for duplicate headings rather than producing split counts (D-02) |
| Effort rollup as labeled points (small=1, medium=3, large=8) | Categorical strings can't be summed; bucket mapping provides relative estimate; rendered as "N pts (s=1 m=3 l=8)" in footer so unit is visible to operator (D-05) |
| Separate `commands/milestone.md` file | Keeps concern isolated; `/ticket-list` stays focused on listing |
| All bash variable expansions double-quoted; `set -euo pipefail` | Prevents word-splitting on extracted values; halts on unexpected grep failures (D-03) |

## Test Strategy

Unit test scenarios are realized as standalone bash scripts in `tests/` that exercise isolated helper functions extracted from `commands/milestone.md` as sourced bash functions, invoked via `bash -c`. Integration tests glob a fixture `.tickets/` tree and assert rendered output matches expected strings.

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | `_milestones.md` with 2 milestones using `## milestone:` prefix: both names extracted |
| FR-1b       | Unit        | `_milestones.md` with a `## Notes` heading: not extracted as a milestone name |
| FR-2        | Unit        | `status.md` with `milestone: v2.0`: field extracted correctly in single-pass read |
| FR-3        | Unit        | Two `milestone:` fields in one file: first value used, second ignored |
| FR-4        | Integration | Fixture with 3 milestones and 8 tagged tickets; `/milestone` table shows all 3 rows with correct counts |
| FR-5        | Integration | `/milestone v2.0`: detail view lists correct tickets with status and effort |
| FR-6        | Integration | `/ticket-list --milestone v2.0`: only v2.0 tickets shown |
| FR-7        | Integration | Ticket without `milestone:` absent from all milestone views; present in unfiltered `/ticket-list` |
| FR-8        | Integration | `_milestones.md` absent: setup message printed, no error or stack trace |
| FR-9        | Integration | `--milestone unknown` on `/ticket-list`: "No tickets found for milestone 'unknown'." printed |
| FR-10       | Unit        | 2 tickets missing `effort:`: rollup treats them as 0 pts; warning "2 tickets have no effort estimate" shown |
| FR-10b      | Unit        | Done ticket with `effort: large` excluded from remaining-effort sum; only non-done tickets counted |
| FR-11       | Unit        | Milestone with 0 tickets: 0% completion, "no tickets assigned" note in table |
| FR-12       | Integration | Summary table sorted alphabetically: "alpha" before "beta" before "v2.0" |
| FR-AC       | Integration | Ticket with `milestone: v2.0` in `status.md` but no matching entry in `_milestones.md`: shown with "(undefined)" in `/ticket-list --milestone v2.0`; `/milestone` summary does NOT show an "v2.0" row; `/milestone v2.0` prints "milestone not found" |
| FR-VAL      | Unit        | `milestone:` value with shell metacharacter (e.g., `$(echo)`): flagged as "(invalid-name)", not executed |
| FR-DUP      | Unit        | `_milestones.md` with duplicate `## milestone: v2.0` heading: warning on stderr, counts not split, stdout table unaffected |
| FR-DUP-ERR  | Unit        | Duplicate-heading warning appears on stderr not stdout; stdout output parses as valid table |
| NFR-1       | Integration | Fixture with 200 status files and 20 milestones on developer hardware: collection + aggregation under 3 seconds (CI runners exempt if documented) |
| NFR-3       | Unit        | Milestone name >30 chars truncated with `…` in summary table |

## Tradeoffs

- **Chose `## milestone: Name` over plain `## Name`**: Reduces spurious-match risk for any `## ` heading the operator adds. Slightly less terse but dramatically more defensible.
- **Chose single-pass `cat` over per-field grep**: Eliminates ~600 subprocess spawns at 200 tickets; reads each file once. Tradeoff: the collection bash step is more complex (parse multiple fields from one read).
- **Chose effort-as-labeled-points over raw display**: `small|medium|large` can't be summed; bucket map must be defined in the design. Rendered with legend ("s=1 m=3 l=8") so operator knows the unit.
- **Chose separate `commands/milestone.md`**: `/milestone` is analytics-focused; mixing into `/ticket-list` would couple listing and reporting concerns.
- **Accepting risk of**: milestone name typos creating ticket-to-milestone mismatches. Mitigated by "(undefined)" annotation on orphaned tickets.

## Risks

- **Milestone name typos in `status.md`**: A ticket with `milestone: v 2.0` won't match `milestone: v2.0`. Mitigation: "(undefined)" annotation in all milestone views surfaces mismatches.
- **Blast radius of `commands/problem.md` template edit**: If step 1 conflicts with 0007's `effort:` addition, the implementer must merge carefully. Mitigated by explicit dependency note.
- **`effort:` absent from legacy tickets**: Expected; zero-contribution with warning count is the specified behavior. No migration needed.
- **Field schema replication across command files**: `milestone:`, `effort:`, `status:` field names are repeated in grep patterns across all command files. A rename requires touching all files. Acknowledged systemic risk — no field registry exists today.
- **Bash shell safety**: All extracted values double-quoted in every expansion; milestone names validated before use; `set -euo pipefail` in collection step. Implementer must not deviate.

## Implementation Order

1. Add `milestone:` (optional) to the `status.md` template in `commands/problem.md`. If 0007 is already merged, only add `milestone:`; `effort:` will already be present.
2. Write `commands/milestone.md` bash collection step: read each `status.md` once with `cat`; parse all needed fields in one awk pass; validate milestone name charset; emit tab-separated records.
3. Write `_milestones.md` parser: grep `^## milestone: ` prefix; warn on duplicates; produce milestone name list.
4. Add aggregation logic: group by validated milestone name; compute done count, total, remaining-effort sum (non-done tickets only); map effort buckets.
5. Add summary table rendering (alphabetically sorted, name truncation, `0%` edge case, "no tickets assigned" note, labeled effort footer).
6. Add detail view rendering for `/milestone <name>` (ticket list with #, title, status, effort; effort-sum footer with legend and warning count).
7. Add `--milestone <name>` filter to `commands/ticket-list.md` (requires 0007 merged). Validate `<name>` argument against safe charset before use. Handle undefined milestone with "(undefined)" annotation.
8. Write integration tests: fixture `.tickets/` tree + `_milestones.md`; cover all FR and AC rows above including NFR-1 timing check.
9. Write unit tests: field parsing, name validation, effort-bucket mapping, done-ticket exclusion from rollup, name truncation, duplicate-heading warning.

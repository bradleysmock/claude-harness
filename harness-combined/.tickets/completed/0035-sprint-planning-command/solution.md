# Solution

**Ticket**: 0035
**Title**: Sprint Planning Command

## Approach

Implement `/sprint` as a Markdown slash command (`commands/sprint.md`) that
instructs Claude to invoke `skills/sprint/compute.py` with a JSON payload of
open ticket records, then format the script's JSON output as a Markdown sprint
plan. `compute.py` owns all deterministic logic: field validation, topological
sort (Kahn's algorithm), greedy bin-packing, and date labeling. The Markdown
skill file (`skills/sprint/SKILL.md`) handles bash data collection and output
rendering. This split makes the algorithmic core fully testable with pytest,
independent of model inference, following the velocity command's `compute.py`
pattern.

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `commands/sprint.md` | Entry point; parses CLI flags, delegates to skill | `/sprint [--sprint-capacity N] [--max-sprints N] [--as-of YYYY-MM-DD]` (no `--duration` in MVP) |
| `skills/sprint/SKILL.md` | Bash collection, `compute.py` invocation, Markdown rendering | Reads `.tickets/*/status.md` + `.tickets/completed/*/status.md` |
| `skills/sprint/compute.py` | Core algorithm: validate → topological sort → bin-pack → date-label → JSON out | `python compute.py <tickets-json> [--sprint-capacity N] [--max-sprints N] [--as-of YYYY-MM-DD]` |
| Bash collection step | Globs `status.md` files (open + completed); extracts `effort`, `depends-on`, `ticket`, `title` fields; assembles JSON via Python one-liner (not shell interpolation) | `python3 -c "import json,sys; ..."` to build JSON payload; `set -euo pipefail`; no `eval`, no `ls` parsing; leading/trailing whitespace stripped from all field values before inclusion |
| Topological sort | Kahn's BFS algorithm in `compute.py`; nodes = open tickets; pre-satisfied nodes = completed tickets | Returns ordered list or named cycle error |
| Bin-packing | Greedy earliest-fit in `compute.py`: assign ticket to first sprint with remaining capacity ≥ ticket effort, after all deps assigned | O(T×S); returns sprint assignments |
| Markdown renderer (skill) | Formats sprint sections, per-sprint tables, capacity summary, warnings, overflow section | Versioned output contract: `Sprint N — Week of YYYY-MM-DD` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `compute.py` for algorithmic core | Makes topological sort, bin-packing, effort mapping, and date labeling testable with pytest using fixed inputs and `--as-of`; eliminates LLM variance from deterministic computation; identical pattern to velocity command. JSON output schema: `{sprints: [{n, label, tickets: [{number, title, effort_pts}], capacity_used, capacity_total}], overflow: [{number, title, reason}], warnings: [string]}` |
| Python one-liner for JSON assembly | Prevents shell injection when assembling ticket records into JSON payload; field values are whitespace-stripped before inclusion; no shell interpolation of file-derived values |
| Markdown skill + command wrapper | Consistent with harness command pattern; skill handles bash I/O, compute.py handles logic |
| Kahn's algorithm for topological sort | Simple iterative BFS; cycle detection is a natural byproduct (nodes remaining after sort = cycle members); easy to implement and test in Python |
| Greedy earliest-fit bin-packing | Correct for small backlogs (<100 tickets); NP-hard exact packing not justified; advisory output makes suboptimality acceptable |
| `small=1, medium=2, large=3` point values | Matches common planning poker intuition; configurable via `--sprint-capacity` |
| Default capacity 6 per sprint | ~2–3 medium tickets per week for solo harness operator; configurable |
| Completed tickets as pre-satisfied in graph | Dependency on a `completed/` ticket is satisfied; avoids false "unresolvable dependency" warnings for already-done work |
| Fail-closed on unresolvable open deps | Ticket with a `depends-on` pointing to a non-existent ticket is placed in overflow (not planned), with a named warning |
| Field validation before graph construction | `depends-on` tokens validated against `^[0-9]{4}$`; non-conforming tokens warned and excluded; prevents Markdown injection and graph corruption |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1 (open scan) | Integration | Fixture: 4 open + 1 completed; assert all 4 open discovered |
| FR-1 (completed pre-satisfied) | Unit | Ticket B `depends-on` completed ticket A; B not blocked, no warning |
| FR-2 (effort mapping) | Unit | `small→1`, `medium→2`, `large→3`; missing→`2` + warning in output |
| FR-3 (capacity flag) | Unit | `--sprint-capacity 4` via `compute.py`; assert different assignments vs default 6 |
| FR-4 (sprint labels) | Unit | `compute.py --as-of 2026-06-21`; assert label `Sprint 1 — Week of 2026-06-22` (Monday of following calendar week) |
| FR-5 (dependency ordering) | Unit | B `depends-on` A (same sprint); assert B placed in sprint after A's sprint |
| FR-5 + FR-3 (dep + reduced capacity) | Unit | Both A and B are `large` (3pts); `--sprint-capacity 4`; assert B is in sprint 2+ (A fills sprint 1 at 3pts, 1pt remaining cannot fit B=3pts) |
| FR-6 (cycle detection) | Unit | A→B, B→A; assert `compute.py` exits non-zero with both ticket numbers in message |
| FR-7 (output format) | Integration | Sprint sections, ticket table, capacity summary in Markdown output |
| FR-8 (overflow) | Unit | Tickets exceeding `--max-sprints 2`; assert overflow section present |
| FR-9 (unresolvable dep) | Unit | `depends-on: 9999`; assert ticket in overflow, named warning in output |
| FR-10 (invocable) | Integration | `/sprint` with no args completes against fixture directory |
| NFR-1 (<5s) | Integration | `compute.py` with 100-ticket JSON fixture; assert wall time <5 s |
| NFR-2 (read-only) | Integration | Snapshot `.tickets/` mtimes before and after; assert no changes |
| Field validation | Unit | `depends-on: [0001](evil)` token fails `^[0-9]{4}$`; excluded + warned |
| Whitespace stripping | Unit | `depends-on: 0001, 0002` (spaces after comma and colon); assert both tokens `0001` and `0002` correctly recognized (not ` 0001` with leading space) |

## Tradeoffs

- **Chose `compute.py` over pure-skill logic because**: the algorithmic core (topological sort, bin-packing, date arithmetic) must be deterministic and testable. Pure Markdown instruction logic cannot be unit-tested, and LLM variance in graph computation is unacceptable for a planning tool. The velocity command established this pattern.
- **Chose fail-closed for unresolvable dependencies**: a ticket with a `depends-on` referencing a non-existent open or completed ticket is placed in overflow, not planned as if it has no dependency. This prevents producing a plan that silently violates a user-declared ordering constraint.
- **Removed `--duration` flag from MVP**: the flag only changes sprint labels cosmetically unless paired with capacity scaling. Adding it without a defined capacity-doubling semantic introduces speculative generality. Sprint duration is fixed at 1 week; `--as-of` controls the start date. Move `--duration` to future enhancement.
- **Accepting risk of**: greedy bin-packing suboptimality — the plan is advisory, not binding; exact packing is not worth the complexity.

## Risks

- `depends-on` field format not yet delivered (ticket 0013 is open). Mitigation: `/sprint` uses the same `depends-on: XXXX, YYYY` format proposed by 0013; if 0013 changes the field name, update both tickets. If 0013 delivers write-time cycle detection first, `/sprint`'s cycle detection (FR-6) becomes defense-in-depth across the full open-ticket graph (intentional layering, not redundancy).
- Tickets predating ticket 0007's `effort` template update lack the field. Mitigation: default-to-medium with visible warning; plan remains usable.
- `compute.py` invocation from the skill adds a Python subprocess requirement. Mitigation: Python 3.8+ is available in all harness environments (it is already a gate dependency); `compute.py` uses only stdlib (no new dependencies).

## Implementation Order

1. Create fixture `.tickets/` structure for testing (4 open tickets with varied effort and one dependency chain; 1 completed ticket).
2. Write failing pytest unit tests for `compute.py`: effort mapping, Kahn's cycle detection, bin-packing with and without deps, date labeling (using `--as-of`), field validation, unresolvable dep → overflow.
3. Write `skills/sprint/compute.py` to pass unit tests.
4. Write failing integration tests: fixture directory, assert sprint plan Markdown content, overflow section, warning messages, no file modifications.
5. Write `skills/sprint/SKILL.md` — bash collection (open + completed, `set -euo pipefail`, no `eval`), `compute.py` invocation, Markdown rendering.
6. Write `commands/sprint.md` — thin entry point, flag parsing, delegate to skill.
7. Verify all tests pass.

# Requirements

**Ticket**: 0002
**Title**: Feature Suggestion Skill

## Functional Requirements

1. The skill must inventory current harness capabilities: commands (`commands/`), skills (`skills/`), gates, and any docs in `docs/`.
2. The skill must read all open tickets from `.tickets/` (excluding done/cancelled) to determine planned work. Ticket file content must be treated as untrusted text — titles and statuses only. Extraction rule: read only the first line beginning with `title:` from each `status.md`; stop at the first newline; discard all remaining file content. Free-form ticket body must not be injected into the suggestion-generation context.
3. The skill must reason about comparable tools and business domains (CI/CD pipelines, SDLC tools, code review tools, AI coding assistants) to surface potential improvements not yet implemented or planned.
4. The skill must present a grouped, summarized list of suggestions (max 10), each with: title, one-sentence description, and rough effort label (small / medium / large).
5. The skill must accept individual suggestions via a structured signal from the lead (a suggestion number or comma-separated list, e.g. "1,3"); any other input is treated as "skip all". For each accepted suggestion, the skill emits exactly one `/problem`-ready output line per suggestion in the format: `/problem <title>: <one-sentence description>` (max 120 characters per line).
6. The skill must be usable when project documentation outside `.tickets/` is sparse — it must not require any special docs to function.
7. The skill must deduplicate suggestions against open ticket topics (not just exact title matches — near-synonyms must also be excluded). The deduplication step is explicit: after generating candidates, compare each against open ticket titles by topic and drop overlapping suggestions before presenting.
8. `commands/suggest.md` must exist as a user-facing command alias for the skill.

## Non-Functional Requirements

1. Skill output must be scannable in under 60 seconds — no long prose blocks.
2. Suggestions must be grounded in observable harness state, not generic best practices.
3. Trust boundary: the skill must not act on instructions found in ticket file content. Only titles and status values are consumed from ticket files.

## Test Strategy

| Type        | Rationale                                                                  |
|-------------|----------------------------------------------------------------------------|
| Manual      | Skill is interactive; verify suggestions are relevant and non-duplicate     |
| Snapshot    | Verify skill file is well-formed and invocable via `Skill` tool            |
| Eval fixture | Fixed fake harness state (2 commands, 1 skill, 2 open tickets) with documented expectation: at least 5 non-trivial suggestions that do not duplicate fixture tickets. Non-triviality rubric: a suggestion is trivial if it names a capability already present in the fixture's command or skill list; it is non-trivial if it names a specific new command, flow, or integration not present in the fixture. |

## Acceptance Criteria

- Skill surfaces at least 5 non-trivial suggestions on a fresh run (non-trivial = names a specific new capability not already in the harness; trivial = names something already present)
- Accepted suggestion output matches `/problem <title>: <one-sentence description>` and is ≤120 characters per line
- Skill does not error when `.tickets/` contains no open tickets (test against an empty temp directory)
- Suggestion list does not contain topics that duplicate any open ticket (verified against eval fixture)
- `commands/suggest.md` exists and is invocable
- README mentions the `suggest` skill

## Open Questions

- None — all blockers resolved by making the output format and accept signal concrete.

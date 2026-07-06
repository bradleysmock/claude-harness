# Solution

**Ticket**: 0027
**Title**: Ticket template customization

## Approach

Extend `commands/problem.md` to (1) load a per-category template from `.tickets/_templates/<type>.md` when `--type` is supplied or inferred, (2) read a `## Custom Sections` block from `.tickets/_standards.md` and inject those stubs into all three artifact writes. Both features are purely additive: the pipeline falls back to the existing scaffold when neither source is present.

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| Template loader | Reads `.tickets/_templates/<type>.md`, extracts `## Section` headings | Re-validates `type` against canonical allow-list `{bug, feature, refactor}` internally before constructing any path (defense in depth — does not rely solely on caller). Returns list of `(heading, body_stub)` pairs or empty list. Returns empty list if `type` fails internal check. |
| Category inferrer | Maps free-text description to canonical category via keyword heuristics; validates `--type` against canonical allow-list `{bug, feature, refactor}` | Returns `(category, confidence)`. Rejects any value not in the three-value allow-list and falls back to generic scaffold with a warning. `chore` and `docs` are not in the active allow-list for this ticket; they are reserved as extension points documented in Tradeoffs. |
| Custom sections loader | Parses first `## Custom Sections` block from `_standards.md` (first occurrence wins; subsequent occurrences are ignored) | Returns list of `(heading, body_stub)` pairs. Validates: (a) heading not in the reserved scaffold headings exclusion list (see Reserved Headings below); (b) individual stub body ≤ 10 lines; (c) total custom sections ≤ 5. Colliding or oversized stubs are dropped with a warning. |
| Section merger | Pure transformation: appends injected sections to a scaffold document | Returns merged document string. No side-effects, no I/O. |
| Line limit enforcer | Accepts a document and a per-artifact line limit; truncates if needed | Returns `(document, truncated_sections_list)`. `truncated_sections_list` is always a list (empty `[]` when no truncation — never null). No logging inside this component. |
| Status writer | Writes `status.md` including `type:` field | Interface: `write_status(ticket, title, branch, date, category, inferred: bool)`. Writes `type: <category>` or `type: generic` when no category applies. |
| `problem.md` command | Orchestrates: validate/infer type → load template → load custom sections → merge → enforce limits → write artifacts → write status | Handles `truncated_sections_list` from limit enforcer by logging named truncated sections to the lead. |

## Tech Choices

| Choice | Rationale |
|---|---|
| Markdown heading extraction (regex `^## .+`) | No new dependency; templates are simple markdown files |
| Keyword heuristics for category inference (3 canonical: bug, feature, refactor) | Sufficient for the three categories named in the problem statement; avoids LLM call overhead; `chore` and `docs` are documented extension points, not built in |
| Allow-list validation before path construction | Prevents path traversal; raw `--type` value is validated against `{bug, feature, refactor}` before any filesystem operation |
| Additive injection (append after last standard section) | Prevents template from breaking required scaffold structure; templates cannot override reserved headings |
| Structured result from limit enforcer | Decouples truncation detection from logging; orchestrator decides how to surface the warning |
| `type:` field added to `status.md` | Provides traceability of inferred/supplied category without changing artifact formats |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | `_templates/bug.md` present → sections appear in `problem.md` |
| FR-2a       | Unit        | `--type feature` resolves `feature.md`; `--type ../../escape` is rejected, falls back to generic with warning |
| FR-2b       | Unit        | Unknown `--type` value falls back to generic |
| FR-3        | Unit        | "login page crashes" infers `bug`; "add dark mode" infers `feature`; ambiguous text infers `none` |
| FR-4a       | Integration | `_standards.md` with `## Custom Sections` → stubs in `problem.md` (correct position, 40-line limit applied) |
| FR-4b       | Integration | `_standards.md` with `## Custom Sections` → stubs in `requirements.md` (correct position, 60-line limit applied) |
| FR-4c       | Integration | `_standards.md` with `## Custom Sections` → stubs in `solution.md` (correct position, 80-line limit applied) |
| FR-4d       | Unit        | Stub heading matching reserved heading (e.g., `## Problem`) → dropped with warning, not injected |
| FR-5        | Integration | No `_templates/`, no custom sections → output byte-identical to current baseline |
| FR-6        | Unit        | Template with `## Reproduction Steps` → section present in artifact |
| FR-7        | Unit        | Empty template file → ticket created, warning logged, no crash |
| NFR-1       | Benchmark   | 100-iteration benchmark of template-loader with absent `_templates/` dir; assert p95 < 10ms on local SSD; CI runners use relaxed 50ms threshold or skip and treat as documented performance goal |
| NFR-2       | Unit        | Template that would exceed 40-line limit → `truncated_sections_list` non-empty; orchestrator logs named sections |
| status.md   | Unit        | `--type bug` → `type: bug` in status.md; inferred `bug` → `type: bug (inferred)`; no match → `type: generic` |

## Tradeoffs

- **Chose keyword heuristics over LLM classification**: avoids latency and cost for a simple 3-class problem (bug/feature/refactor); false positives degrade gracefully (falls back to generic). `chore` and `docs` are intentionally excluded from the active allow-list in this ticket — they are reserved extension points to be activated in a future ticket with their own keyword sets and templates.
- **Chose additive-only injection**: prevents leads from accidentally overwriting required scaffold sections; downside is that leads cannot reorder core sections via templates.
- **Chose `## Custom Sections` sub-block in `_standards.md`**: reuses an existing file rather than adding a new config file; downside is that `_standards.md` conflates engineering standards prose with structural metadata. First occurrence of `## Custom Sections` wins; subsequent occurrences are ignored.
- **Chose structured result from limit enforcer over internal logging**: decouples truncation detection from the logging strategy; orchestrator owns the logging decision and surfaces named truncated sections to the lead.
- **Chose defense-in-depth allow-list in template loader**: template loader re-validates `type` internally even though the inferrer already validated it; this closes the layer gap for future call sites.
- **Accepting risk of**: template drift — if a lead renames a template file, inference still runs but silently gets no template; mitigated by the `type:` field in `status.md` making the mismatch visible.

## Reserved Headings (Custom Sections Exclusion Lists)

These headings cannot be used in `_standards.md` custom section stubs. Any stub whose heading matches (case-insensitive) is dropped with a warning.

| Artifact | Reserved headings |
|---|---|
| `problem.md` | Problem, Impact, Success Criteria, Out of Scope |
| `requirements.md` | Functional Requirements, Non-Functional Requirements, Tech Stack, Test Strategy, Acceptance Criteria, Open Questions |
| `solution.md` | Approach, Components, Tech Choices, Test Plan, Tradeoffs, Risks, Implementation Order |

This list is also user-visible documentation: leads must know which headings they cannot override when writing `_standards.md`.

## Risks

- `_standards.md` parsing is fragile if the lead does not use exact `## Custom Sections` heading — mitigated by case-insensitive match and a clear spec in docs.
- Line-limit truncation could silently drop critical stubs — mitigated by structured `truncated_sections_list` result surfaced to the lead by the orchestrator.
- Reserved heading collision in custom stubs — mitigated by exclusion-list check in custom sections loader before injection.

## Implementation Order

1. Add template loader with allow-list validation precondition: parse `.tickets/_templates/<type>.md` → list of `(heading, stub)` pairs; unit tests first including path-traversal rejection.
2. Add category inferrer with allow-list check on `--type`: keyword map → `(category, confidence)` for bug/feature/refactor; unit tests for 3 canonical categories + ambiguous case + invalid `--type` value.
3. Add custom sections loader (renamed from "standards section extractor"): parse `## Custom Sections` block from `_standards.md`; validate heading exclusion list, stub body ≤ 10 lines, count ≤ 5; unit tests including reserved-heading collision.
4. Add section merger (pure): accepts scaffold + injected sections list → returns merged document string; unit tests.
5. Add line limit enforcer (pure): accepts document + limit → returns `(document, truncated_sections_list)`; unit tests including truncation edge case.
6. Add status writer component: writes `status.md` with `type:` field; unit tests for supplied/inferred/generic cases.
7. Wire into `commands/problem.md` orchestrator: validate/infer type → load template → load custom sections → merge → enforce limits → write artifacts → write status → log any truncated sections.
8. Integration test: full `/problem` run with template + custom standards sections; full run with no templates (regression baseline).

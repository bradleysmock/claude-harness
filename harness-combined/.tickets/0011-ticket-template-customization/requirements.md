# Requirements

**Ticket**: 0011
**Title**: Ticket template customization

## Functional Requirements

1. The system must support a `.tickets/_templates/` directory where leads can place per-category template files (e.g., `bug.md`, `feature.md`, `refactor.md`).
2. The system must accept an optional `--type <category>` flag on `/problem` invocations. The value must be validated against the canonical allow-list `{bug, feature, refactor}` (three values; `chore` and `docs` are reserved extension points not active in this ticket) before any filesystem operation. An invalid value causes the pipeline to fall back to the generic scaffold with a warning — no file path is constructed from an unvalidated caller-supplied string. The template loader must also re-validate the type internally (defense in depth) before constructing any path.
3. The system must infer the ticket category from the request description when `--type` is not supplied, using a canonical set of three categories: `bug`, `feature`, `refactor`. (`chore` and `docs` are reserved as documented extension points but are not built into the inferrer in this ticket.) If inference confidence is low, the generic scaffold is used with no template applied.
4. The system must read `.tickets/_standards.md` for a `## Custom Sections` block that defines additional section stubs. Before injection, the system must: (a) reject any stub whose heading matches a reserved scaffold heading; (b) enforce a maximum stub body length of 10 lines; (c) enforce a maximum of 5 custom sections total. Rejected stubs are dropped with a warning. Accepted stubs are injected into each of `problem.md`, `requirements.md`, and `solution.md` for every new ticket.
5. The system must fall back to the existing generic scaffold unchanged when no `_templates/` directory and no custom sections in `_standards.md` are present.
6. Template files must be plain markdown; any `## <Section>` heading in a template becomes an additional section in the corresponding artifact.
7. The system must skip a template silently (with a logged warning) if the template file is present but empty or unparseable; the ticket is still created with the generic scaffold.

## Non-Functional Requirements

1. Template loading must complete in under 10ms (p95, 100 iterations) on a local SSD when no `_templates/` directory exists, measured from the first function call to return of the template loader. CI runners use a relaxed 50ms threshold or may skip and treat this as a documented performance goal. This is a benchmark-tested requirement.
2. The injected sections must not exceed the artifact line limits (40 lines for `problem.md`, 60 lines for `requirements.md`, 80 lines for `solution.md`); if a template would push an artifact over the limit, the system must truncate injected sections and surface the names of truncated sections to the lead via the orchestrator.

## Tech Stack

Not applicable — this is an extension to an existing markdown-and-shell pipeline; no new runtime or framework is introduced.

## Test Strategy

| Type        | Rationale                                                                 |
|-------------|---------------------------------------------------------------------------|
| Unit        | Template loading, category inference, section merging, fallback behavior  |
| Integration | End-to-end `/problem` run with and without templates and custom sections   |

## Acceptance Criteria

- Running `/problem --type bug` with a `bug.md` template present produces a `problem.md` that includes the template's sections alongside the standard scaffold.
- Running `/problem` without `--type` on a clearly bug-shaped description infers `bug` and applies `bug.md` if present.
- Running `/problem` with no templates and no `_standards.md` custom sections produces output identical to the current baseline.
- Custom sections defined in `_standards.md` appear in all three artifacts (`problem.md`, `requirements.md`, `solution.md`) for every new ticket.
- An empty or missing template file does not crash the pipeline; the ticket is created with the generic scaffold.

## Open Questions

**Decision: inferred category in `status.md`** — Yes. A `type:` field is added to `status.md` for every ticket. Value is `<category>` when supplied via `--type`, `<category> (inferred)` when inferred from description, and `generic` when no category applies. This provides traceability for template drift detection.

**Decision: template injection mode** — Additive only. Templates cannot override or reorder reserved scaffold sections (`## Problem`, `## Impact`, `## Success Criteria`, etc.). Custom stubs are appended after the last standard section. This prevents accidental corruption of required structure.

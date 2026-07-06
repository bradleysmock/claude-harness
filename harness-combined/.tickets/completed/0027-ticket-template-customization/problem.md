# Problem Statement

**Ticket**: 0027
**Title**: Ticket template customization
**Date**: 2026-06-21

## Problem

When `/problem` is invoked, it always generates the same generic scaffolding regardless of ticket category (bug, feature, refactor, etc.). Leads have no way to inject project-specific sections — such as "affected service" or "rollout plan" — into every new ticket without manually editing each artifact after creation. This creates repetitive manual work and allows required fields to be missed.

## Impact

- Harness operators must manually add project-specific fields to every ticket, increasing the chance of omissions.
- Ticket quality varies across categories because there is no category-aware scaffolding (e.g., a bug ticket missing reproduction steps, a feature ticket missing rollout plan).
- Teams cannot encode institutional knowledge about what every ticket must contain.

## Success Criteria

- A `.tickets/_templates/` directory can hold per-category template files (e.g., `bug.md`, `feature.md`, `refactor.md`).
- When `/problem` is invoked with `--type <category>`, the matching template pre-populates the `problem.md` scaffold with category-specific prompts.
- When `--type` is not supplied, the category is inferred from the request description; if inference is ambiguous, the generic scaffold is used.
- `_standards.md` can define custom sections that are injected into `problem.md`, `requirements.md`, and `solution.md` for every new ticket, regardless of category.
- Tickets created without any template or custom sections are identical in output to the current behavior (no regression).

## Out of Scope

- Retroactively updating existing ticket files with new template content.
- UI or interactive template selection (e.g., prompts mid-run).
- Validating template file syntax beyond basic markdown parsing.

# Problem Statement

**Ticket**: 0038
**Title**: Tech Stack Advisor
**Date**: 2026-06-21

## Problem

When `/build` or `/autopilot` generates code for a new application, microservice, or UI, the tech stack is chosen implicitly based on LLM training-data frequency rather than the project's actual constraints — team expertise, existing conventions, runtime environment, performance requirements, or organizational preferences. The lead only discovers the chosen stack after implementation has begun, at which point changing it requires a rework.

## Impact

- **Lead engineers** waste time correcting generated code that used the wrong framework, language version, or tooling after the fact.
- **New projects** drift away from org standards because there was no prompt to check before generating.
- **Consistency** degrades across microservices in a monorepo when each `/build` picks a slightly different stack without consulting the lead.

## Success Criteria

- When a new app/service/UI is detected in a `/problem` or `/build` invocation, the harness surfaces a tech stack proposal with explicit rationale for each choice before generating implementation code.
- The lead can approve, modify, or reject the proposal inline before `/build` proceeds.
- The proposal draws on `_standards.md` (if populated) and explicit signals from the request (language, framework, constraints mentioned) rather than defaulting to training-data frequency.
- The approved stack is recorded so subsequent `/build` runs on the same ticket do not re-ask.
- Existing tickets with an already-specified `Tech Stack` section in `requirements.md` are not re-prompted.

## Out of Scope

- Retroactively changing the stack for tickets already in `implementing` or later status.
- Automated dependency version pinning (a separate concern).
- Stack selection for non-code artifacts (documentation-only tickets).

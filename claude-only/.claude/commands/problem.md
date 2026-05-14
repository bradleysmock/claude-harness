Entry point for new work. Runs the full pre-implementation pipeline autonomously and stops at checkpoint 1 for lead approval.

If `.tickets/_learnings.md` exists, load it via @.tickets/_learnings.md as context — past must-fix patterns inform this round.
If `.tickets/_conventions.md` exists, load it via @.tickets/_conventions.md as context — project conventions to respect.

---

## Phase 0 — Clarity Check

Read the request. If any of the following are missing or too vague to proceed, ask targeted questions and stop — do not guess:

- **Who is the user or consumer?** (e.g. "admin", "anonymous visitor", "CLI operator")
- **What is the concrete outcome?** A fuzzy goal like "improve the dashboard" is not enough — what specifically changes?
- **What does done look like?** Is there a clear success condition or acceptance signal?
- **What is out of scope?** If scope is totally undefined, clarify before continuing.

If the request is sufficiently clear, proceed without asking. Do not ask questions for the sake of it.

---

## Phase 1 — Claim Ticket Number

Ticket number assignment must be atomic to prevent two concurrent agents from claiming the same number.

1. Check for a lock file at `.tickets/.ticket.lock`. If it exists, wait 2 seconds and check again. Retry up to 5 times. If still locked after 5 retries, stop and report the conflict to the lead.

2. Write `.tickets/.ticket.lock` with a timestamp to claim the lock.

3. Read `.tickets/NEXT_TICKET` if it exists — this is the next available number. If the file does not exist, scan `.tickets/` for all existing ticket directories, find the highest number, and compute the next one. Start at `0001` if no tickets exist.

4. Record the claimed number as XXXX.

5. Write the incremented value back to `.tickets/NEXT_TICKET`.

6. Delete `.tickets/.ticket.lock` to release the lock.

Now create the ticket directory and files.

---

## Phase 2 — Problem

Write `.tickets/XXXX-<slug>/problem.md` (hard limit: 40 lines — use bullets, not prose):

```markdown
# Problem Statement

**Ticket**: XXXX
**Title**: <short human-readable title>
**Date**: YYYY-MM-DD

## Problem

<2–4 sentences. Focus on the problem, not the solution.>

## Impact

<Who is affected and how. What goes wrong without a solution.>

## Success Criteria

<Bullet list: what must be true when this is resolved.>

## Out of Scope

<Bullet list: explicit exclusions. Omit section if nothing is excluded.>
```

Write `.tickets/XXXX-<slug>/status.md`:

```
status: problem
ticket: XXXX
title: <title>
branch: ticket/XXXX-<slug>
updated: YYYY-MM-DD
```

---

## Phase 3 — Requirements

Based on `problem.md`, derive requirements without asking the lead. Flag genuine blockers in the Open Questions section rather than stopping.

Write `.tickets/XXXX-<slug>/requirements.md` (hard limit: 60 lines — omit sections that don't apply):

```markdown
# Requirements

**Ticket**: XXXX
**Title**: <title>

## Functional Requirements

<Numbered list. Each item is a testable statement: "The system must...">

## Non-Functional Requirements

<Numbered list. Include performance, security, accessibility as applicable. Omit if none.>

## Tech Stack

<Only for new applications. Language, runtime, frameworks, tooling.>

## Test Strategy

| Type        | Rationale                          |
|-------------|------------------------------------|
| Unit        | <what is tested at unit level>     |
| Integration | <what is tested at integration>    |

## Acceptance Criteria

<Bullet list. Binary pass/fail.>

## Open Questions

<Genuine blockers that cannot be reasonably inferred. Empty if none.>
```

Update `status.md` to `status: requirements`.

---

## Phase 4 — Solution

Draft the solution covering: approach, components, tech choices with rationale, test plan, tradeoffs, risks, and implementation order.

Write `.tickets/XXXX-<slug>/solution.md` (hard limit: 80 lines — use tables and bullets, not prose; omit sections that don't apply):

```markdown
# Solution

**Ticket**: XXXX
**Title**: <title>

## Approach

<2–4 sentences describing the solution at a high level.>

## Components

<Table or bullet list: component name, responsibility, key interfaces>

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| ...    | ...       |

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1        | Unit        | <what is tested>       |
| FR-2        | Integration | <what is tested>       |

## Tradeoffs

- **Chose X over Y because**: ...
- **Accepting risk of**: ...

## Risks

<Bullet list with mitigations where known.>

## Implementation Order

<Ordered list of steps for /implement to follow directly.>
```

Update `status.md` to `status: solution`.

---

## Phase 5 — Critic Loop

Before spawning the critic, verify that all three artifact files exist and are non-empty:
- `.tickets/XXXX-<slug>/problem.md`
- `.tickets/XXXX-<slug>/requirements.md`
- `.tickets/XXXX-<slug>/solution.md`

If any file is missing or empty, fix the write before proceeding.

Spawn the **critic subagent** (`subagent_type: critic`) with this brief:

> Phase: **design**
> Ticket: **XXXX-<slug>**
> Round: **1** (max 2)
>
> Follow `@.claude/critic-brief.md`. The artifact files to review are:
>
> - `.tickets/XXXX-<slug>/problem.md`
> - `.tickets/XXXX-<slug>/requirements.md`
> - `.tickets/XXXX-<slug>/solution.md`
>
> You are reviewing documents, not code — apply expert lenses at the design level. Add these design-specific evaluations on top of the standard brief:
>
> 1. **Requirements coverage** — does the solution address every FR and success criterion? Are acceptance criteria testable as designed?
> 2. **Test plan gaps** — what scenarios would the loaded panels' experts flag as missing?
> 3. **Tech choices** — are there better-fit alternatives given the constraints?
> 4. **Security design** — apply McGraw: are trust boundaries correct? Does the design fail closed?
> 5. **Implementation order risks** — dependencies or sequencing that could cause rework.

Revise `solution.md` based on the critic's findings. If significant issues were raised, verify the revised file is fully written, then spawn a second critic round with `Round: 2`. **Maximum 2 rounds.**

---

## Phase 6 — Spec Score Check

Before presenting Checkpoint 1, run `/score-spec XXXX`. If the verdict is BLOCK, include the failed checks in the checkpoint summary under "Spec issues" and flag that the lead should reject or request rework. If WARN, list the warnings but proceed.

---

## Checkpoint 1 — Present to Lead

Present a concise summary and wait for approval:

```
## Checkpoint 1: Ready to implement?

**Ticket**: XXXX — <title>

### What was decided
<2–4 bullets: approach and key tech choices>

### What the critic found
<How many rounds, what categories of issues, how resolved. "No significant issues" if clean.>

### Open questions
<Any unresolved items from requirements. Empty if none.>

---
Approve to begin implementation? (yes / no / feedback)
```

Do not proceed to `/implement XXXX` until the lead approves.

> **Session boundary**: After approval, the lead should `/clear` (or start a new Claude Code session) before running `/implement XXXX`. This keeps the implementation phase context lean.

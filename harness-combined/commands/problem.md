Entry point for new work. Runs the full pre-implementation pipeline autonomously and stops at checkpoint 1 for lead approval.

**Standards gate (fail-closed).** Before loading any standards context, if `.tickets/_standards.md` exists, validate it first:

```
python3 "${CLAUDE_PLUGIN_ROOT}/validators/standards_validator.py" .tickets/_standards.md
```

A non-zero exit **halts** the pipeline — show the validator's stderr (the missing or stubbed sections) and stop; do not run any generative phase until `.tickets/_standards.md` is filled in. This call runs **before** the `@.tickets/_standards.md` load below, so stub content never enters context on a failing run.

If `.tickets/_standards.md` exists, load it via @.tickets/_standards.md as context — project engineering standards.
If `.tickets/_learnings.md` exists, load it via @.tickets/_learnings.md as context — past must-fix patterns the lead has captured.

Both files are lead-curated. The machine's separate BM25 failure trail at `.harness/memory.db` is opaque and consulted only by `memory(action="retrieve", ...)` during gate repair — do not surface its contents here.

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

`Clarity check · Claim ticket · Problem · Requirements · Tech-stack advisor (if new app) · Solution · Critic loop · Checkpoint 1`

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

Ticket number assignment must be atomic across developers. A claim is a small commit to `main` that is pushed immediately — first-push-wins; a loser re-numbers and retries. The claim commit is also the durable "work started / number taken" signal other developers see on `main`.

1. Acquire the local lock `.tickets/.ticket.lock` (format `pid:epoch`) exactly as before — it serializes multiple agents on *this* machine and avoids wasted round-trips. Treat a lock whose timestamp is >60s old or whose pid is dead (`kill -0 <pid>` nonzero) as stale and delete it; otherwise `sleep 2` and retry up to 5 times, then report the conflict.

2. Claim the number with the `ticket.py claim` helper (it scans both `.tickets/*` and `.tickets/completed/*` for the next number, writes the stub `status.md` with `status: claimed`, `title`, `branch`, and `owner:` from `git config user.email`, commits `chore(ticket): XXXX claim`, and — when an `origin` exists — pushes; on a rejected push it rebases, re-numbers, and retries up to 5 times). **Only after the winning push** does it create the branch `ticket/XXXX-<slug>` and worktree `.worktrees/XXXX-<slug>` — so a renumber-on-reject leaves no orphaned branch or worktree (create-after-push):

   `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" claim <slug> "<title>" --push`

   The command prints the claimed `XXXX-<slug>`. Record XXXX. If it exits non-zero after retries, stop and report the conflict to the lead.

3. Release the lock: `rm -f .tickets/.ticket.lock`.

The claim commit is the **only** `main` commit the ticket writes before delivery. The ticket directory now exists with a `claimed` stub on `main`, and the branch `ticket/XXXX-<slug>` + worktree `.worktrees/XXXX-<slug>` exist for the rest of the design and build. **Phases 2–4 write `problem.md`, `requirements.md`, and `solution.md` into the worktree (`.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/`) and commit+push them on the branch — never to `main`.**

---

## Phase 2 — Problem

> **All Phase 2–4 artifact writes go into the worktree, on the branch.** Every `.tickets/XXXX-<slug>/...` path named in Phases 2–4 below is the worktree-qualified path `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/...`. Writing to `main`'s bare `.tickets/` path would leave the design uncommitted on `main` (the orphaned-metadata failure the guard catches) and violate the branch-only invariant. Commit + push them on the branch in Phase 5.

Write `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/problem.md` (hard limit: 40 lines — use bullets, not prose):

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

Update `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/status.md` (the claim stub is already there — edit it in place):

```
status: solution
ticket: XXXX
title: <title>
branch: ticket/XXXX-<slug>
owner: <git config user.email>
source: local
external_id:
updated: YYYY-MM-DD
```

---

## Phase 3 — Requirements

Based on `problem.md`, derive requirements without asking the lead. Flag genuine blockers in the Open Questions section rather than stopping.

Write `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/requirements.md` (hard limit: 60 lines — omit sections that don't apply):

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

## Phase 3.5 — Tech Stack Advisor

Read and follow `${CLAUDE_PLUGIN_ROOT}/context/flows/stack-advisor.md`.

This sub-procedure fires between Phase 3 and Phase 4. It detects whether the request describes a new application, microservice, or UI component; if so, proposes a tech stack for lead approval before any implementation files are written. The approved stack is recorded in `requirements.md § Tech Stack`.

Skip conditions (handled inside the flow):
- The ticket's `requirements.md` already has a populated `## Tech Stack` section → flow exits immediately.
- `--no-stack-check` was passed in the `/problem` invocation → flow exits immediately.

If either skip condition fires (or confidence is not high), the flow exits and Phase 4 begins normally.

---

## Phase 4 — Solution

Draft the solution covering: approach, components, tech choices with rationale, test plan, tradeoffs, risks, and implementation order.

Write `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/solution.md` (hard limit: 80 lines — use tables and bullets, not prose; omit sections that don't apply):

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

<Ordered list of implementation steps. This is what /build uses to determine spec order.>
```

Update `status.md` to `status: solution`.

---

## Phase 5 — Critic Loop

Before spawning the critic, verify that all three artifact files exist and are non-empty (in the worktree, where Phases 2–4 wrote them):
- `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/problem.md`
- `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/requirements.md`
- `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/solution.md`

If any file is missing or empty, fix the write before proceeding.

Spawn the **critic subagent** (`subagent_type: critic`) with this brief:

> Phase: **design**
> Ticket: **XXXX-<slug>**
> Round: **1** (max 2)
>
> Follow `@${CLAUDE_PLUGIN_ROOT}/context/critic-brief.md`. The artifact files to review are (in the worktree):
>
> - `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/problem.md`
> - `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/requirements.md`
> - `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/solution.md`
>
> You are reviewing documents, not code — apply expert lenses at the design level. Add these design-specific evaluations on top of the standard brief:
>
> 1. **Requirements coverage** — does the solution address every FR and success criterion? Are acceptance criteria testable as designed?
> 2. **Test plan gaps** — what scenarios would the loaded panels' experts flag as missing?
> 3. **Tech choices** — are there better-fit alternatives given the constraints?
> 4. **Security design** — apply McGraw: are trust boundaries correct? Does the design fail closed?
> 5. **Implementation order risks** — dependencies or sequencing that could cause rework.

Revise `solution.md` based on the critic's findings. If significant issues were raised, verify the revised file is fully written, then spawn a second critic round with `Round: 2`. **Maximum 2 rounds.**

### Commit the design artifacts (on the branch)

Once the critic loop is complete and `solution.md` is final, commit the three artifacts **on the feature branch inside the worktree** and push — never to `main` (see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). The claim commit was already the ticket's one pre-delivery `main` commit; the design lives on the branch and reaches `main` only via the delivery squash:

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX design (status: solution)"
git -C .worktrees/XXXX-<slug> push    # publish the design on the branch for other developers
```

If the lead requests changes at Checkpoint 1 and you revise the artifacts, commit the revision the same way (on the branch) before continuing.

---

## Phase 6 — Spec Score Check

Present Checkpoint 1 once the critic loop is complete.

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

Do not proceed until the lead approves.

> **Session boundary**: After approval, the lead should `/clear` (or start a new Claude Code session) before running `/write-spec XXXX` then `/build XXXX`. This keeps the implementation phase context lean.

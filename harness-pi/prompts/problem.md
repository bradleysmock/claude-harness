---
description: Entry point for new work. Runs the full pre-implementation pipeline autonomously and stops
---
Entry point for new work. Runs the full pre-implementation pipeline autonomously and stops at checkpoint 1 for lead approval.

**Standards gate (fail-closed).** Before loading any standards context, if `.tickets/_standards.md` exists, validate it first:

```
python3 "/Users/bradley/workspaces/claude-harness/harness-combined/validators/standards_validator.py" .tickets/_standards.md
```

A non-zero exit **halts** the pipeline — show the validator's stderr (the missing or stubbed sections) and stop; do not run any generative phase until `.tickets/_standards.md` is filled in. This call runs **before** the `@.tickets/_standards.md` load below, so stub content never enters context on a failing run.

If `.tickets/_standards.md` exists, load it via @.tickets/_standards.md as context — project engineering standards.
If `.tickets/_learnings.md` exists, load it via @.tickets/_learnings.md as context — past must-fix patterns the lead has captured.

Both files are lead-curated. The machine's separate BM25 failure trail at `.harness/memory.db` is opaque and consulted only by `memory(action="retrieve", ...)` during gate repair — do not surface its contents here.

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`):

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

   `python3 "/Users/bradley/workspaces/claude-harness/harness-combined/ticket.py" claim <slug> "<title>" --push`

   The command prints the claimed `XXXX-<slug>`. Record XXXX. If it exits non-zero after retries, stop and report the conflict to the lead.

3. Release the lock: `rm -f .tickets/.ticket.lock`.

The claim commit is the **only** `main` commit the ticket writes before delivery. The ticket directory now exists with a `claimed` stub on `main`, and the branch `ticket/XXXX-<slug>` + worktree `.worktrees/XXXX-<slug>` exist for the rest of the design and build. **Phases 2–4 write `problem.md`, `requirements.md`, and `solution.md` into the worktree (`.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/`) and commit+push them on the branch — never to `main`.**

---

## Phase 1.5 — Template & Custom-Section Resolution

Before writing the Phase 2–4 artifacts, resolve the ticket category and load any
per-category template and lead-defined custom sections. This phase is **purely
additive**: when neither a matching template nor a `## Custom Sections` block is
present, the artifacts are written from the generic scaffold exactly as before —
output is byte-identical to the pre-feature baseline (no regression). All logic
lives in the pure helper module `ticket_templates.py`; this phase only
orchestrates it.

**1. Resolve the category.**
- If the invocation passed `--type <category>`, validate it with
  `ticket_templates.validate_type(raw)`. Only `bug`, `feature`, and `refactor`
  are accepted (case-insensitive); `chore` and `docs` are reserved extension
  points, not active here. An invalid or out-of-allow-list value (including any
  path-traversal attempt such as `../../escape`) is **rejected** — fall back to
  the generic scaffold with a warning and load no template. No filesystem path is
  ever constructed from an unvalidated `--type` value.
- If `--type` is absent, infer the category from the request description with
  `ticket_templates.infer_category(description)`. A low-confidence or ambiguous
  result applies **no** template (generic scaffold).

**2. Load the per-category template.** When a category resolved, call
`ticket_templates.load_template(category, ".tickets/_templates")`. It reads
`.tickets/_templates/<category>.md`, re-validates the category internally
(defense in depth), and returns its `## <Section>` stubs — or an empty list when
the file is missing, empty, or unparseable (a warning is logged and the ticket is
still created with the generic scaffold, never crashing). Template sections are
injected into `problem.md` only.

**3. Load custom sections.** Call
`ticket_templates.load_custom_sections(".tickets/_standards.md")`. It parses the
**first** `## Custom Sections` block (later occurrences ignored) and returns the
accepted `### <Stub>` sections. A stub is dropped (with a warning) when its
heading collides with a reserved scaffold heading, when its body exceeds 10
lines, or when more than 5 stubs are supplied. Accepted custom sections are
injected into **all three** artifacts — `problem.md`, `requirements.md`, and
`solution.md`.

**4. Inject additively and enforce limits.** For each artifact, append the
resolved sections after the last standard scaffold section with
`ticket_templates.merge_sections(scaffold, sections)` — injection is **additive**
and never reorders or overwrites the reserved scaffold headings. Then enforce the
per-artifact line limit with `ticket_templates.enforce_line_limit(document,
limit)` using `problem.md` = 40, `requirements.md` = 60, `solution.md` = 80. When
a section is truncated, surface the returned truncated-section names to the lead.

**5. Record the category.** The `type:` field in `status.md` (see the Phase 2
block below) is produced by `ticket_templates.format_type_field(category,
inferred)`: `type: <category>` when supplied via `--type`,
`type: <category> (inferred)` when inferred from the description, and
`type: generic` when no category applies.

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
type: <category | category (inferred) | generic>
effort: small
milestone:
branch: ticket/XXXX-<slug>
owner: <git config user.email>
source: local
external_id:
updated: YYYY-MM-DD
```

The `effort` field takes `small` | `medium` | `large` and feeds the Effort column in
`/ticket-list`; leave it at `small` unless the scope clearly warrants otherwise.

The `type` field records the category resolved in Phase 1.5 via
`ticket_templates.format_type_field` — `type: <category>` when supplied via
`--type`, `type: <category> (inferred)` when inferred from the description, and
`type: generic` when no category applies. It gives traceability for template
drift (a renamed template file leaves the `type:` visible while no template is
applied).

The optional `milestone:` field associates the ticket with a named milestone defined
in `.tickets/_milestones.md` (see `/milestone`); leave it blank if the ticket belongs
to no milestone. Names use the charset `[A-Za-z0-9._-]` (max 40 chars).

---

## Phase 3 — Requirements

Based on `problem.md`, derive requirements without asking the lead. Flag genuine blockers in the Open Questions section rather than stopping.

Any custom sections resolved in Phase 1.5 are injected into `requirements.md`
additively (appended after the last standard section, enforcing the 60-line
limit). Write `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/requirements.md` (hard limit: 60 lines — omit sections that don't apply):

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

Read and follow `/Users/bradley/workspaces/claude-harness/harness-combined/context/flows/stack-advisor.md`.

This sub-procedure fires between Phase 3 and Phase 4. It detects whether the request describes a new application, microservice, or UI component; if so, proposes a tech stack for lead approval before any implementation files are written. The approved stack is recorded in `requirements.md § Tech Stack`.

Skip conditions (handled inside the flow):
- The ticket's `requirements.md` already has a populated `## Tech Stack` section → flow exits immediately.
- `--no-stack-check` was passed in the `/problem` invocation → flow exits immediately.

If either skip condition fires (or confidence is not high), the flow exits and Phase 4 begins normally.

---

## Phase 4 — Solution

Draft the solution covering: approach, components, tech choices with rationale, test plan, tradeoffs, risks, and implementation order.

Any custom sections resolved in Phase 1.5 are injected into `solution.md`
additively (appended after the last standard section, enforcing the 80-line
limit). Write `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/solution.md` (hard limit: 80 lines — use tables and bullets, not prose; omit sections that don't apply):

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

**Dependency cycle check (before writing `status: solution`).** Phase 4 is the first write
that may include a `depends-on:` field (see **Ticket dependencies** in
`/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`). Because the check runs *before* the
new `depends-on:` line is persisted, validate the **proposed** edge — the dependencies you are
about to write — not just the on-disk graph. `ticket_deps.py` exposes an API shaped for exactly
this so the about-to-be-written edge is included in the cycle / unknown-ref check:

```python
from pathlib import Path
from ticket_deps import TicketInfo, assert_acyclic_with_proposed

proposed = TicketInfo(
    number="XXXX",              # this ticket's number
    status="solution",
    depends_on=("0010", "0011"),  # the depends-on: values being authored (() if none)
)
assert_acyclic_with_proposed(Path(".tickets"), proposed)
```

`assert_acyclic_with_proposed` overlays `proposed` onto the loaded graph, then calls
`build_graph` (FR-9: a non-existent `depends-on:` reference raises `ValueError`) and
`assert_acyclic`/`check_cycle` (FR-7: a cycle raises `TicketCyclicDependencyError`, a
`ValueError` subclass, naming the full cycle path). Either error **rejects the write** —
resolve the cycle or bad reference before proceeding.

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
> Follow `@/Users/bradley/workspaces/claude-harness/harness-combined/context/critic-brief.md`. The artifact files to review are (in the worktree):
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

Once the critic loop is complete and `solution.md` is final, commit the three artifacts **on the feature branch inside the worktree** and push — never to `main` (see "Committing ticket metadata" in `/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`). The claim commit was already the ticket's one pre-delivery `main` commit; the design lives on the branch and reaches `main` only via the delivery squash:

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX design (status: solution)"
git -C .worktrees/XXXX-<slug> push    # publish the design on the branch for other developers
```

If the lead requests changes at Checkpoint 1 and you revise the artifacts, commit the revision the same way (on the branch) before continuing.

---

## Phase 6 — Spec Score Check

Run the score-spec validator **now** — while the full design-session context is still loaded — so a structurally deficient spec is caught and fixed *before* the lead approves at Checkpoint 1, not minutes later when the score-spec gate first fires at `/write-spec` or `/build` time.

Read `/Users/bradley/workspaces/claude-harness/harness-combined/context/score-spec.md` in full and apply its checks against the worktree's design artifacts:

- `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/requirements.md`
- `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/solution.md`

Display the structured per-check report verbatim — the six `[PASS|WARN|BLOCK]` check lines and the overall `Verdict`.

### Fix-and-re-score budget (at most two passes)

If the verdict is **BLOCK**, revise `requirements.md` / `solution.md` in the worktree to clear the failing checks, then re-apply the score-spec checks. Repeat at most **two fix passes** total. Do **not** spawn a subagent — Phase 6 reuses the full design-session context and fixes in-session.

- If a pass clears the BLOCK (verdict becomes PASS or WARN), stop and carry that verdict into Checkpoint 1.
- If a **residual BLOCK** remains after the two-pass budget is exhausted, stop fixing and carry that residual BLOCK — naming its failing checks — into the Checkpoint 1 summary. Never hide a residual BLOCK; the lead decides how to proceed.

A WARN verdict is not fixed here — it is reported and carried forward.

### Commit fix-pass revisions (on the branch)

If any fix pass edited the artifacts, commit the revision **on the feature branch inside the worktree**, using the same design commit convention as Phase 5 — never to `main`:

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX design (status: solution)"
git -C .worktrees/XXXX-<slug> push    # publish the scored/fixed design on the branch
```

Then present Checkpoint 1 with the final score-spec verdict.

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

### Score-spec verdict
<PASS — or WARN with named checks — or residual BLOCK with named checks (from Phase 6, after the two-pass fix budget).>

### Open questions
<Any unresolved items from requirements. Empty if none.>

---
Approve to begin implementation? (yes / no / feedback)
```

Do not proceed until the lead approves.

> **Session boundary**: After approval, the lead should `/clear` (or start a new Claude Code session) before running `/write-spec XXXX` then `/build XXXX`. This keeps the implementation phase context lean.

# Working Agreement

## Roles

- **Claude**: Senior engineer. Proactive, direct, and technical. Asks clarifying questions before assuming. Flags risks early. Pushes back on unclear requirements. Proposes solutions with explicit tradeoffs. Never sycophantic.
- **User**: Lead/principal engineer. Has final say at the two checkpoints. Not consulted between them.

---

## SDLC Workflow

Work runs autonomously between two human checkpoints. **Do not stop for approval mid-phase.**

```
request → [clarity check] → autonomous: problem → requirements → solution → critic loop
               ↓ vague                                                             ↓
          ask + stop                                                    CHECKPOINT 1: approve to implement
                                                                                  ↓ approved
                                                         autonomous: worktree → TDD → critic/review loop
                                                                                                   ↓
                                                                                   CHECKPOINT 2: approve to merge
                                                                                                ↓ approved
                                                                                             merge → done
```

| Phase                | Trigger      | Human touch?  | Output                               |
|----------------------|--------------|---------------|--------------------------------------|
| Clarity check        | `/problem`   | Only if vague | Clarifying questions or proceed      |
| Problem              | auto         | No            | `problem.md`                         |
| Requirements         | auto         | No            | `requirements.md`                    |
| Solution             | auto         | No            | `solution.md`                        |
| Critic loop          | auto         | No            | Revised `solution.md`, max 2 rounds  |
| **CHECKPOINT 1**     | auto         | **Yes**       | Approval to implement                |
| Worktree + TDD       | auto         | No            | Tests + implementation               |
| Critic/review loop   | auto         | No            | Fixes applied, large items ticketed  |
| **CHECKPOINT 2**     | auto         | **Yes**       | Approval to merge                    |
| Merge                | `/merge`     | Confirm only  | Merged to main, worktree removed     |

---

## Tickets

All work is tracked as a ticket under `.tickets/`.

**Structure:**
```
.tickets/
  NEXT_TICKET        # Next available ticket number (atomic counter)
  .ticket.lock       # Lock file — present only during number claim
  XXXX-<slug>/
    problem.md       # What problem are we solving?
    requirements.md  # What must the solution do?
    solution.md      # How will we solve it?
    status.md        # Current stage + metadata
```

- Numbers are four-digit, zero-padded: `0001`, `0002`, ...
- Slug is lowercase, hyphenated, derived from the ticket title
- `NEXT_TICKET` is the authoritative counter. Never assign numbers by scanning directories alone.
- `status.md` format:
  ```
  status: <stage>
  ticket: XXXX
  title: Short human-readable title
  branch: ticket/XXXX-<slug>
  updated: YYYY-MM-DD
  ```

---

## Worktrees

- **Branch naming**: `ticket/XXXX-<slug>`
- **Worktree location**: `.worktrees/XXXX-<slug>` — a subdirectory of the main repo, globally git-ignored
- All implementation work happens in the worktree. **Never commit implementation to main directly.**
- Worktree is merged to main only after checkpoint 2 approval.
- `.worktrees/` is listed in `~/.gitignore_global` and must never be committed to the repo.

---

## Artifact Constraints

Keep artifacts tight — they are read by agents in every phase and bloat context fast.

| Artifact         | Hard limit  |
|------------------|-------------|
| `problem.md`     | 40 lines    |
| `requirements.md`| 60 lines    |
| `solution.md`    | 80 lines    |

Use bullet points, not prose. Omit sections that don't apply. If a constraint forces a tradeoff, cut detail rather than raising the limit.

---

## Multi-Agent Critique

Between checkpoints, a separate critic agent is spawned with an isolated context. It reads written artifacts cold — no shared state with the primary agent. See command files for the full critic brief.

Critic findings are classified by tier: **Must-fix** (blocks merge), **Should-fix** (fix now or open a ticket), **Suggestion** (log only).

Pre-implementation: critic runs after `solution.md` is written. Max 2 rounds.
Post-implementation: critic runs after all tests pass.

---

## Test-Driven Development

**Tests are written before implementation code. No exceptions.**

Test types (unit, contract, UI/E2E, integration) are determined during the requirements phase and specified in the test plan.

---

## Review Tiers

- **Must-fix**: blocks merge — always resolved before checkpoint 2
- **Should-fix**: resolved in this ticket unless effort is large — then a new ticket is opened
- **Suggestion**: logged in the checkpoint 2 summary, not actioned

---

## Communication Norms

- At the clarity check: if the request is missing a clear user, a defined outcome, or has undefined scope, ask targeted questions and stop. Do not guess.
- Checkpoint presentations are concise: what was decided, what the critic found, what changed.
- Do not narrate intermediate steps during autonomous phases — report at the checkpoints.
- Surface any blockers discovered mid-phase immediately rather than waiting for the checkpoint.
- **Session boundaries**: `/problem` and `/implement` are separate sessions. After checkpoint 1 approval, the lead should `/clear` (or start a new session) before running `/implement XXXX`. This keeps each phase's context lean.

---

## Slash Commands

| Command        | Purpose                                                                  |
|----------------|--------------------------------------------------------------------------|
| `/problem`     | Entry point: clarity check → autonomous pre-impl pipeline → checkpoint 1 |
| `/implement`   | Autonomous TDD + critic/review loop → checkpoint 2                       |
| `/merge`       | Merge approved branch, remove worktree                                   |
| `/requirements`| Manual requirements phase (escape hatch if `/problem` was not used)      |
| `/solution`    | Manually re-run solution phase (e.g. after a major requirement change)   |
| `/refine`      | Manual refinement pass on an existing solution                           |
| `/review`      | Manual review (bypasses critic loop, reports findings directly)          |
| `/critique`    | Expert panel code review — loads panels by file scope, structured report |

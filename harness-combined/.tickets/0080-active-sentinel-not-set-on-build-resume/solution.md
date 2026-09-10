# Solution

**Ticket**: 0080
**Title**: Set .tickets/.active on the normal /build resume path

## Approach

`build-ticket.md` Step 2 currently writes `.tickets/.active` only inside its
rare fallback branch, with a bare relative path that's ambiguous about cwd.
Move the write to one unconditional line that both the normal-resume and
fallback paths fall through to — immediately before the `status:
implementing` transition, the one line both paths already share — using
the explicit worktree-relative path `.worktrees/XXXX-<slug>/.tickets/.active`
so it always lands where `server.py`'s `standards_path` derivation (and
therefore the coverage gate's `_active_ticket_dir`) actually looks.

## Components

| Component | Responsibility |
|---|---|
| `context/flows/build-ticket.md` Step 2 | One unconditional `.active` write, correct explicit path, before the `implementing` transition; remove the now-redundant fallback-only echo |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| One write point before the shared `implementing` transition, not two | Both the normal and fallback paths reach that line; a single unconditional write there can't be missed by either path, and removes the duplicate-with-different-path risk |
| Explicit `.worktrees/XXXX-<slug>/.tickets/.active` over a bare `.tickets/.active` | Matches `server.py`'s actual resolution (`<directory>/.tickets/_standards.md`'s parent) — the ambiguous bare form is exactly what caused this ticket |

## Test Plan

| Requirement | Test Type  | Scenario(s) |
|-------------|------------|--------------|
| FR-1/FR-2   | Doc-wiring | Step 2 documents the unconditional, worktree-relative `.active` write |
| FR-3        | Doc-wiring | no remaining bare `.tickets/.active` (cwd-ambiguous) reference in Step 2 |
| FR-4/FR-5   | Doc-wiring | cycle-check code block and `implementing` transition/push language unchanged; `deliver-ticket.md`/`autopilot-batch.md` files untouched (diff-scoped to `build-ticket.md` only) |

## Tradeoffs

- **Chose a doc-only fix over adding a Python helper because**: writing one
  sentinel file is not a "two runs must agree" exactness operation — it's a
  single `echo`, already the existing convention (per the LLM/Python
  boundary rule in CLAUDE.md).

## Risks

- None beyond the file touched — a single doc section, no code path change.

## Implementation Order

1. Doc-wiring tests for the corrected Step 2 text — red first.
2. Edit `build-ticket.md` Step 2: one unconditional, correctly-pathed
   `.active` write; remove the redundant fallback-only echo.
3. Confirm tests green; confirm no other Step 2 content changed.

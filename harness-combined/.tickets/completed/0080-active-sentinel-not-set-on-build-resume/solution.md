# Solution

**Ticket**: 0080
**Title**: Set .tickets/.active on the normal /build resume path

## Approach

`build-ticket.md` Step 2 currently writes `.tickets/.active` only inside its
rare fallback branch, with a bare relative path that's ambiguous about cwd.
Add one unconditional line **immediately after the "Resume that worktree"
sentence and before the cycle-check code block** — i.e. at the same
repo-root cwd every other Step 2 prose line up to that point assumes, and
textually *before* both the cycle-check block and the fallback block, so
it reads unambiguously as "runs once here regardless of which branch
follows," never groupable with the later `# cwd = .worktrees/XXXX-<slug>`
`set-status` block. It uses the explicit repo-root-relative path
`.worktrees/XXXX-<slug>/.tickets/.active` — placing this write inside the
`# cwd = ...` block instead would resolve that same explicit path one
level too deep (`<worktree>/.worktrees/XXXX-<slug>/.tickets/.active`),
reintroducing this exact bug unconditionally rather than only in the rare
fallback. The fallback branch's own now-redundant `echo` line is removed.

`build-ticket.md` Step 1's `changes-requested` resume skips Step 2
entirely on a repair re-run — a no-op for this fix, not a gap: the
sentinel written by that ticket's *earlier* Step 2 run already names this
same worktree/ticket and nothing clears it mid-repair-cycle (the worktree
itself isn't removed until a terminal transition), so no invariant breaks.

## Components

| Component | Responsibility |
|---|---|
| `context/flows/build-ticket.md` Step 2 | One unconditional `.active` write, at repo-root cwd, positioned before the cycle-check block; remove the now-redundant fallback-only echo |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Write point *before* the cycle-check block, not grouped with the `# cwd = .worktrees/XXXX-<slug>` block | The two blocks have different, explicitly-stated cwd semantics in the existing doc; placing the new line anywhere near the worktree-cwd block risks the exact double-nesting bug this ticket exists to fix — placing it earlier, at the still-repo-root point, removes that ambiguity entirely |
| Explicit `.worktrees/XXXX-<slug>/.tickets/.active` over a bare `.tickets/.active` | Matches `server.py`'s actual resolution (`<directory>/.tickets/_standards.md`'s parent) — the ambiguous bare form is exactly what caused this ticket |

## Test Plan

| Requirement | Test Type  | Scenario(s) |
|-------------|------------|--------------|
| FR-1/FR-2   | Doc-wiring | Step 2 documents the unconditional, worktree-relative `.active` write |
| FR-1/FR-2   | Doc-wiring | the new write's line position is *before* the cycle-check block and strictly before the `# cwd = .worktrees/XXXX-<slug>` annotation — not just present anywhere in Step 2 — so a misplacement into the worktree-cwd block would fail this test, not just an absence check |
| FR-3        | Doc-wiring | no remaining bare `.tickets/.active` (cwd-ambiguous) reference in Step 2 |
| FR-4/FR-5   | Doc-wiring | cycle-check code block and `implementing` transition/push language unchanged; `deliver-ticket.md`/`autopilot-batch.md` files untouched (diff-scoped to `build-ticket.md` only) |

## Tradeoffs

- **Chose a doc-only fix over adding a Python helper because**: writing one
  sentinel file is not a "two runs must agree" exactness operation — it's a
  single `echo`, already the existing convention (per the LLM/Python
  boundary rule in CLAUDE.md).

## Risks

- **Cwd misplacement re-introduces the bug unconditionally.** If the new
  write line is grouped with the `# cwd = .worktrees/XXXX-<slug>` block
  instead of placed before the cycle-check block, the explicit path
  resolves one level too deep and every `/build` writes to a nonexistent
  nested path instead of just the rare fallback branch. Mitigated by the
  Test Plan's line-position assertion (relative to the `# cwd` annotation),
  not just a presence check.

## Implementation Order

1. Doc-wiring tests for the corrected Step 2 text — red first.
2. Edit `build-ticket.md` Step 2: one unconditional, correctly-pathed
   `.active` write; remove the redundant fallback-only echo.
3. Confirm tests green; confirm no other Step 2 content changed.

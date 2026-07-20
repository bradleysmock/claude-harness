# Requirements

**Ticket**: 0067
**Title**: Incremental critic rounds: rounds 2+ review repair diff, not the full worktree

## Functional Requirements

1. Critic round 1 of a build's Step 7 (and any `/problem` Phase 5 design-review round) must retain its current full-worktree / full-artifact scope — no behavior change.
2. For each repair-loop round N+1 spawned from `build-ticket.md` Step 7a (N ≥ 1), the critic subagent must be invoked in an **incremental** mode whose brief embeds (a) the round's own diff (the just-committed repair commit's diff) and (b) the prior round's BLOCKER/MAJOR findings — instead of an instruction to read the full worktree.
3. The prior round's BLOCKER/MAJOR findings must be recovered by parsing `critic-findings.md`'s latest (`## Round N`) section with the existing `gates.critic_finding_parser.parse_critic_findings` (ticket 0062) — no second, independent finding-parsing implementation.
4. `critic-brief.md` Step 1 (panel loading) for an incremental round must scope `panel_detect.py`'s file-list argument to the diff's touched files only, not the full worktree's file set.
5. `critic-brief.md` Step 2.5's requirements-coverage and solution-alignment checks must be skipped on incremental rounds — both are whole-artifact judgments already established at round 1 that don't shrink meaningfully to a diff.
6. `critic-brief.md` Step 2.5's weakened/deleted-tests check must **stay active** on incremental rounds, scoped to the diff's touched test files, and must retain Read access to `solution.md`'s Test Plan section to compare against — the NFR's "don't re-embed full worktree content" constraint governs the brief's file-content payload, not which ticket-baseline files a still-active Step 2.5 sub-check is permitted to read. `gates/repair_integrity.py` deliberately does not flag a same-file "balanced swap" (a real test removed, a dummy test added, netting to zero); its own docstring names this Step 2.5 check as the acknowledged backstop for that pattern, and a repair round under pressure to turn BLOCKER/MAJOR findings green is the highest-risk moment for it.
7. The critic must verify a prior BLOCKER/MAJOR finding's fix status by reading the current state of its `file:line`, regardless of whether that file lies inside the round's diff — the critic retains full Read/Grep access to the worktree for this purpose. Diff-scoping (FR-4, FR-8 new-finding evaluation) applies only to panel loading and to evaluating *new* findings, never to re-verifying a carried-forward finding.
8. The incremental critic brief must instruct the critic to (a) classify each prior BLOCKER/MAJOR finding as fixed or still-present per FR-7 — a still-present finding must be re-emitted in the same structured `**SEVERITY** · <Panel>/<Dimension> · \`file:line\`` block Step 4 already mandates for every finding, so it remains parseable by `parse_critic_findings` — and (b) evaluate new findings only within the diff's touched files.
9. A new `gates/incremental_scope.py` must provide `touched_files_from_diff(diff_text, worktree_root) -> list[str]` (resolving and containing each parsed path against `worktree_root`, matching `validate_finding`'s / `parse_critic_findings`'s existing containment convention) and `format_incremental_brief(prior_findings, diff_text) -> str`, consumed by `build-ticket.md` Step 7a before spawning the round N+1 critic.
10. If `critic-findings.md`'s latest section parses to zero findings when the prior round's summary reported BLOCKER/MAJOR findings, the round must fail closed to full-worktree scope — reverting **both** the file-content scope **and** the full Step 2.5 check set (requirements coverage, solution alignment, and weakened/deleted tests) together. The skip decisions in FR-5/FR-6/FR-8 key off whether the round's brief is actually incremental, never off the raw `Round >= 2` number alone, so a fail-closed round is never a mix of full-content-scope with checks skipped.

## Non-Functional Requirements

- Incremental-round critic prompts must not re-embed full file contents for files untouched by the round's diff, except where FR-6 or FR-7 require reading a specific ticket-baseline section or prior-finding location outside the diff.
- No change to the `critic-findings.md` on-disk format beyond what 0062 already defines (0067 is a pure consumer of it).

## Tech Stack

N/A — extends the existing Python `gates/` package and markdown flow/brief files; no new runtime or framework.

## Test Strategy

| Type        | Rationale                                                           |
|-------------|----------------------------------------------------------------------|
| Unit        | `touched_files_from_diff` on multi-file / rename / binary diff fixtures, incl. path-containment rejection |
| Unit        | `format_incremental_brief` output is deterministic and includes every prior finding + the diff |
| Integration | Step 7a fixture: round 1 unaffected; round 2 gets incremental brief, correctly reports fixed / still-present / new |
| Integration | A prior finding outside the diff's touched files is read directly and reported persisted, not spuriously fixed by omission |
| Integration | A balanced test swap confined to an incremental round's diff is still caught by the scoped weakened-tests check |
| Integration | Fail-closed fallback round re-enables full Step 2.5, not just full-worktree file content |
| Regression  | Existing `test_critic_reconciler` / `test_critic_finding_parser` (0062) suites stay green |

## Acceptance Criteria

- Round 1 critic prompts are unchanged (no `Mode: incremental` marker, full-worktree instruction retained).
- Round 2+ critic prompts contain the round's diff and the prior round's BLOCKER/MAJOR findings, and do not instruct a full-worktree read.
- Round 2+ panel selection differs from round 1 whenever the diff's touched files trigger a smaller panel set.
- A prior BLOCKER/MAJOR finding located outside the round's diff is still correctly re-verified against its actual current state, never marked fixed solely because it fell outside the diff.
- A round whose diff fully addresses all prior BLOCKER/MAJOR findings and introduces no new ones ends the repair loop (Step 7a item 6) exactly as today.

## Open Questions

- None — ticket 0062 (finding parser/reconciler) is the only hard dependency; it is unbuilt (`status: review-ready`, not yet delivered to `main`) — recorded as `depends-on: 0062`.

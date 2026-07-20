# Solution

**Ticket**: 0067
**Title**: Incremental critic rounds: rounds 2+ review repair diff, not the full worktree

## Approach

Round 1 of every critic invocation (`/build` Step 7, `/problem` Phase 5) keeps its current full-worktree/full-artifact scope unchanged. For repair-loop re-spawns (`build-ticket.md` Step 7a, round N+1), insert a prep sub-step before the spawn: harvest the prior round's BLOCKER/MAJOR findings from `critic-findings.md`'s latest section (reusing ticket 0062's parser), capture the round's own diff, and hand both to the critic as an **incremental** brief. Diff-scoping is narrower than it sounds: panel loading and *new*-finding evaluation are limited to the diff's touched files, but the critic keeps full Read/Grep access to re-verify each *prior* finding's `file:line` wherever it lives — an untouched-but-persisted finding must never be reported "fixed" by omission. Step 2.5's requirements-coverage / solution-alignment checks are skipped (whole-artifact, already established at round 1); its weakened/deleted-tests check stays active, scoped to the diff, since `repair_integrity.py` explicitly does not catch a same-file balanced test swap.

## Components

| Component | Responsibility |
|-----------|-----------------|
| `gates/incremental_scope.py` — `touched_files_from_diff(diff_text, worktree_root)`, `format_incremental_brief()` | Deterministic diff-parsing (with path containment, matching `validate_finding`/`parse_critic_findings`) and brief formatting — exactness ops stay in Python per the LLM/Python boundary rule |
| `build-ticket.md` Step 7a, new sub-step before item 5 | Harvests prior findings (`parse_critic_findings` on `latest_section`), computes the round diff, calls the new module, embeds the result in the round N+1 spawn brief |
| `critic-brief.md` Step 1 / 2.5 / 3 / 4 | New "incremental round" branch: `panel_detect.py` file-list scoped to the diff; Step 2.5 split — coverage/alignment skipped, weakened-tests check retained and diff-scoped; prior-finding verification always reads the finding's actual location; new findings limited to diff-touched files |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Reuse 0062's `parse_critic_findings` / `latest_section` rather than a new parser | Single source for critic-prose parsing; avoids format drift between the reconciler and this new consumer |
| `Round == 1` full scope, `Round >= 2` incremental, keyed off effective scope not raw number | `Round` resets to 1 at the start of every `/build` invocation, so `>=2` means "within this build's repair loop" — but the fail-closed fallback (below) forces a `Round >= 2` brief back to full scope, so the skip decisions actually check "is this brief incremental," not the number itself |
| Split Step 2.5 instead of skipping it wholesale | Requirements coverage / solution alignment don't shrink meaningfully to a diff; the weakened/deleted-tests check is the acknowledged backstop for a same-file "balanced swap" that `repair_integrity.py`'s own docstring says it will not catch — dropping it on repair rounds removes the only defense at the highest-pressure moment for that gaming pattern. It keeps Read access to `solution.md`'s Test Plan section specifically — the brief's "no full file re-embedding" constraint governs payload size, not which ticket-baseline files an active sub-check may open |
| Prior-finding verification is never diff-scoped | `reconcile()` (0062) classifies a prior finding as fixed purely by its *absence* from the current round's parsed findings — if the critic only re-read diff-touched files, every persisted finding outside the diff would silently read as "fixed" |
| Fail-closed fallback reverts file scope and Step 2.5 together | A partial fallback (full file content, checks still skipped) would reintroduce the exact blind spot the fallback exists to close |
| `touched_files_from_diff` takes `worktree_root` and enforces containment | Matches the established signature convention of `gates/finding.py.validate_finding` and `gates/critic_finding_parser.py.parse_critic_findings` in the same package |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-9        | Unit        | `touched_files_from_diff` on multi-file / rename / binary diffs, incl. containment rejection |
| FR-9        | Unit        | `format_incremental_brief` output is deterministic, includes every prior finding + the diff |
| FR-1        | Regression  | Round-1 spawn brief unchanged (no `Mode: incremental` marker) |
| FR-5        | Integration | Incremental brief omits requirements-coverage/solution-alignment instructions (Step 2.5's first two checks not invoked) |
| FR-2, FR-3, FR-8 | Integration | Step 7a fixture: round-2 brief carries diff + prior findings; reports fixed/still-present/new correctly |
| FR-4        | Integration | Round-2 panel set differs from round-1 when the diff touches fewer file types |
| FR-7        | Integration | Prior finding outside the diff's files is read directly and reported persisted, not spuriously fixed |
| FR-6        | Integration | Balanced test swap confined to an incremental round's diff is still caught |
| FR-10       | Integration | Parse-mismatch case falls back to full scope with full Step 2.5 re-enabled |

## Tradeoffs

- **Chose diff-scoped panel loading / new-finding evaluation, full-scope prior-finding re-verification**: cheaper than full-worktree-every-round while closing the "fixed by omission" gap the critic's round-1 reviewer flagged; costs slightly more than a naive diff-only design since prior-finding checks can still touch files outside the diff.
- **Accepting risk of**: an incremental round's diff-scoped panel set under-triggering a panel that mattered for a touched file as a whole, not just its changed lines — mitigated by round 1 already having applied the full panel set once against the same file.

## Risks

- Depends on ticket 0062 (`parse_critic_findings`, `latest_section`, `Finding`) — currently `status: review-ready`, not yet merged to `main`. Recorded as `depends-on: 0062`; `/build 0067` is blocked until 0062 reaches `status: done` (Step 1.9 dependency precondition).
- `critic-brief.md` and `build-ticket.md` are both touched by 0062 and by the craft-polish feature already on `main`, and 0062's own worktree copy of both files predates ticket 0057's `panel_detect.py` rewrite — ground the actual implementation against current `main`, not either worktree's stale copy.

## Implementation Order

1. `gates/incremental_scope.py`: `touched_files_from_diff()` + `format_incremental_brief()` + unit tests.
2. `critic-brief.md`: add the incremental-mode branch (diff-scoped panels via `panel_detect.py`, split Step 2.5, full-scope prior-finding verification, diff-scoped new findings).
3. `build-ticket.md` Step 7a: insert the prep sub-step (harvest prior findings, capture diff, call the new module) before the round N+1 spawn; update the spawn brief text.
4. Integration tests for the Step 7a round-2 fixture (fixed/persisted/new, outside-diff persisted finding, balanced-swap catch, panel-set difference, fail-closed fallback).
5. `harness-reference.md`: document incremental-round behavior alongside the existing critic-loop description.

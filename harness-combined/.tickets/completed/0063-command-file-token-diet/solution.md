# Solution

**Ticket**: 0063
**Title**: Command-file token diet: move helper internals to docstrings; dedupe the critic-round persistence block

## Approach

Two independent, additive-safe edits to markdown command/flow files: (1) collapse
`commands/problem.md`'s Phase 1.5 and dependency-cycle-check sections into
docstring pointers, mirroring the pattern already used at `ticket-status.md:58-68`;
(2) add one canonical "critic-round persistence" block to
`context/harness-reference.md`'s existing "Critic findings file" section, then
replace the 5 near-verbatim restatements in `build-ticket.md` (2 sites) /
`repair-escalation.md` (3 sites) with short references to it. No Python changes, no change
to what an agent actually does — only what it reads to know what to do.

## Components

| File | Change |
|------|--------|
| `commands/problem.md` | Phase 1.5: replace prose restatement with 1-line-per-helper-call + docstring pointer. Dependency-cycle-check: keep code snippet, drop prose restatement, add pointer to `assert_acyclic_with_proposed` docstring. |
| `context/harness-reference.md` | Extend "Critic findings file" (section heading is the anchor; currently ~346-366) with the canonical append-format + commit-command block, generalized with `<section-heading>` / `<commit-message>` placeholders (neutral `.worktrees/XXXX-<slug>` path form — each call site substitutes its own local convention) so all 5 sites can reference it. Note explicitly that body-content shape (3-field diagnosis vs. verbatim structured report) stays covered by the section's existing surrounding prose, not folded into the 2-placeholder template. |
| `context/flows/build-ticket.md` | Step 7, and Step 7a inner step 5: replace full persist blocks with "see 'Critic findings file' in harness-reference.md; heading = `## Round N`, commit = `chore(ticket): XXXX critic findings round N`". |
| `context/flows/repair-escalation.md` | 3 sites — Phase 1 diagnosis persist (`## Escalation diagnosis` heading), Phase 1 critic-round persist, Phase 2 critic-round persist: same reference-replacement, each stating its own heading/commit-message values. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Extend `harness-reference.md`'s existing section rather than a new file | Established pattern already used for `critic-brief.md`; avoids proliferating reference files for one concept. |
| Docstring-pointer over deletion in `problem.md` | Agents following the command file still need to know a step exists and roughly what it does — full deletion would lose that signal. A 1-line-per-call summary + pointer keeps orientation without restating internals. |
| Placeholder-parameterized canonical block (`<section-heading>`, `<commit-message>`) over 5 fully-separate canonical blocks | The 5 sites differ only in heading text, commit message, and (for diagnosis) body shape, which the section's existing prose already covers — one parameterized block avoids re-fragmenting what we just deduped. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1, FR-2  | Content   | Diff `problem.md` before/after; confirm no restated validation-order/truncation prose remains; confirm docstring pointers resolve to real function names in `ticket_templates.py`/`ticket_deps.py`. |
| FR-3        | Content   | Confirm `harness-reference.md`'s block includes append format + commit shape for both `## Round N` and `## Escalation diagnosis` cases. |
| FR-4        | Content   | Grep all 5 call sites for the removed literal git-commit/append-format text; confirm each now contains only the short reference + its varying parameter. |
| FR-5        | Regression| Manually re-walk `/build` Step 7/7a and `repair-escalation.md` Phase 1/2 against the edited files; confirm the sequence of writes/commits an agent would perform is byte-identical in outcome to the pre-edit version. |
| FR-6        | Content   | Confirm `ticket-status.md:58-68` and any other already-correct delegation sites are untouched in the diff. |

## Tradeoffs

- **Chose reference-with-parameters over full deletion**: keeps each call site
  self-orienting (states what varies) at the cost of a few extra words per site
  versus a bare "see harness-reference.md".
- **Accepting risk of**: a future editor forgetting to update the canonical block
  when adding a 5th persistence call site — mitigated by the block now being the
  obvious single edit point, which is the point of this ticket.

## Risks

- Over-trimming `problem.md` could leave an agent unable to act without opening
  `ticket_templates.py` mid-flow — mitigated by keeping a 1-line "what" per helper
  call, not just a bare pointer.
- Line-number references (e.g. "currently lines 346-366") drift as the file
  changes — mitigated by naming the section heading ("Critic findings file") as
  the primary anchor, not the line range.

## Implementation Order

1. Extend `harness-reference.md`'s "Critic findings file" section with the
   canonical, parameterized persistence block.
2. Replace the 2 `build-ticket.md` call sites with references to it.
3. Replace the 3 `repair-escalation.md` call sites (diagnosis, Phase 1 round,
   Phase 2 round) with references to it.
4. Rewrite `problem.md` Phase 1.5 to docstring pointers.
5. Rewrite `problem.md`'s dependency-cycle-check section to a docstring pointer.
6. Run the content/regression checks in Test Plan; capture `git diff --stat` for
   the Success Criteria line-count check.

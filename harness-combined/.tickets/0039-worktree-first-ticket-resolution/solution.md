# Solution

**Ticket**: 0039
**Title**: Worktree-first ticket resolution and branch-only commit fixes

## Approach

Add a "Ticket resolution" subsection to harness-reference.md stating the worktree-first
rule, then sweep the four committing flows and five resolver flows to cite it and to
move all post-claim commits onto the branch. Remove pre-redesign remnants. Guard with a
docs-consistency test in the existing tests/ style (grep-based, like
test_multidev_ticketing_docs.py).

## Components

| Component | Responsibility |
|-----------|----------------|
| harness-reference.md § Ticket resolution | Single authoritative rule, worked example |
| Resolver flow edits (5 files) | Cite + apply the rule in their Step 1 / resolution text |
| Commit-target fixes (4 files) | Branch-side commits for Step A, review Step 7, refine, spec-remediation |
| tests/test_0039_resolution_docs.py | Grep assertions for rule citation and forbidden main commits |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Grep-based docs tests | Matches existing repo pattern for flow-doc invariants |
| Rule lives in harness-reference.md | Already declared the canonical conventions file |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | harness-reference contains the rule section with worktree-first wording |
| FR-2 | Unit | Each of the five resolver files cites the rule section by name |
| FR-3 | Unit | autopilot-ticket Step A contains a `git -C .worktrees/` commit, no root-level add |
| FR-4 | Unit | review SKILL Step 7 and refine.md contain branch-side commit commands only |
| FR-5 | Unit | spec-remediation.md and build-ticket.md contain no "before any worktree is created" text |

## Tradeoffs

- **Chose docs+tests over code enforcement because**: resolution is performed by the
  model reading flows; a hook cannot see intent. The grep tests keep future edits honest.
- **Accepting risk of**: wording drift the greps do not catch; mitigated by anchoring on
  stable phrases.

## Risks

- Editing five resolver flows invites merge conflicts with in-flight tickets — keep each
  edit minimal and additive.

## Implementation Order

1. Write the rule section in harness-reference.md.
2. Fix commit targets: autopilot Step A, review Step 7, refine.md, spec-remediation.md.
3. Remove worktree remnants (spec-remediation.md, build-ticket.md Step 1).
4. Add rule citations to the five resolver flows.
5. Add tests/test_0039_resolution_docs.py; run full test suite.

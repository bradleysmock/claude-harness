# Requirements

**Ticket**: 0039
**Title**: Worktree-first ticket resolution and branch-only commit fixes

## Functional Requirements

1. harness-reference.md must define one ticket-resolution rule: when a worktree exists
   for a ticket, the worktree's .tickets copy of status.md is authoritative; the root
   copy signals only claim and terminal states.
2. The resolver steps in commands/autopilot.md, context/flows/build-ticket.md Step 1,
   context/flows/write-spec-ticket.md Step 1, commands/gate.md, and
   context/flows/deliver-ticket.md Step 1 must cite and apply the resolution rule.
3. autopilot-ticket.md Step A must commit the changes-requested transition inside the
   worktree on the branch, matching build-ticket.md Step 7d, not to main.
4. skills/review/SKILL.md Step 7 and commands/refine.md (interactive Step 5 and
   non-interactive rule 6) must commit status and artifact changes on the ticket branch.
5. context/spec-remediation.md must reflect branch-at-claim: the worktree exists at
   Step S time, remediation commits go to the branch, and the "no worktree yet"
   invariant text is removed; the equivalent remnant in build-ticket.md Step 1 must
   also be removed.

## Non-Functional Requirements

1. No behavior change to claim, squash delivery, or ticket.py.
2. All edits are documentation/flow files; changes must keep each file's existing
   structure and heading order.

## Test Strategy

| Type | Rationale                                                             |
|------|------------------------------------------------------------------------|
| Unit | Docs-consistency tests grep the named files for the rule citation and forbidden main-commit instructions |
| Unit | Regression guard that harness-reference still asserts two-commits-on-main |

## Acceptance Criteria

- Grepping the five resolver flows finds the resolution-rule citation in each.
- No flow file outside deliver/cancel/abandon/claim instructs `git add .tickets/` with a
  commit to main between claim and delivery.
- spec-remediation.md contains no "no worktree" wording.
- Existing tests still pass.

## Open Questions

- None.

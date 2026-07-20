# Problem Statement

**Ticket**: 0073
**Title**: Craft-polish commits use a 'polish:' prefix that commit_lint's default allowed types don't recognize
**Date**: 2026-07-20

## Problem

`context/harness-reference.md`'s Craft Polish Pass section and `build-ticket.md`
Step 7b.5 both specify that each accepted craft round is committed as its own
commit with subject `polish: craft round N`. `gates/commit_lint.py`'s
`DEFAULT_ALLOWED_TYPES` is `("feat", "fix", "docs", "style", "refactor",
"perf", "test", "chore", "build", "ci", "revert")` — `polish` is not in the
list. `/deliver`'s Step 1.5 commit-lint gate therefore fails closed on any
ticket branch that actually picked up a craft-polish commit, discovered while
delivering ticket 0071 (the first ticket, across this repo's full history, to
land a real craft-polish round with non-empty improvements).

## Impact

Any ticket whose craft-polish pass finds and applies at least one improvement
cannot pass `/deliver`'s commit-lint gate without a manual commit-message
rewrite — a silent, easy-to-miss trap for every future ticket, since the craft
subagent and its calling flow have no reason to know commit_lint's allowed-type
set.

## Success Criteria

- A `polish: craft round N` subject passes the default `commit_lint` config
  with no `.tickets/_standards.md` override required.
- Existing allowed types and other commit subjects are unaffected.

## Out of Scope

- Ticket 0071 — the actual craft-polish commit there was rewritten to
  `refactor: 0071 craft round 1 polish` as a workaround, not a fix.
- Re-litigating the `polish:` convention itself (whether it should be `polish`
  vs. reusing `refactor`) — pick whichever resolution keeps the two systems
  consistent; either is acceptable.

# Requirements

**Ticket**: 0063
**Title**: Command-file token diet: move helper internals to docstrings; dedupe the critic-round persistence block

## Functional Requirements

1. `commands/problem.md` Phase 1.5 must state *what* each helper call does (one
   line each) and point to the docstring for *how* — not restate validation order,
   defense-in-depth, or truncation semantics already in `ticket_templates.py`'s
   `validate_type`/`infer_category`/`load_template`/`load_custom_sections`/
   `merge_sections`/`enforce_line_limit`/`format_type_field` docstrings.
2. `problem.md`'s dependency-cycle-check block must reduce to the code snippet plus
   a one-line pointer to `assert_acyclic_with_proposed`'s docstring in `ticket_deps.py`.
3. Exactly one canonical description of "append critic round to
   `critic-findings.md`, commit on branch" (append format + commit shape) must live
   in `harness-reference.md`, extending "Critic findings file" (currently lines 346-366).
4. The 5 existing near-verbatim restatements must be replaced with short references
   to that canonical block, stating only what varies per site (round-number source,
   section heading, commit message): `build-ticket.md` Step 7, `build-ticket.md`
   Step 7a inner step 5, `repair-escalation.md` Phase 1 diagnosis persist,
   `repair-escalation.md` Phase 1 critic-round persist, and
   `repair-escalation.md` Phase 2 critic-round persist.
5. Agent-observable behavior must remain unchanged: same files written, same append
   format, same commit messages, same trigger conditions.
6. Locations that already correctly delegate (e.g. `ticket-status.md:58-68`'s
   pattern) must be left untouched.

## Non-Functional Requirements

- Documentation-only edit; no `.py` file is modified.
- Edited sections remain understandable standalone by an agent that hasn't yet
  read the referenced docstring/reference block.

## Test Strategy

| Type       | Rationale                                                          |
|------------|----------------------------------------------------------------------|
| Content    | Grep-verify no duplicate persistence prose remains outside `harness-reference.md`; verify `problem.md` no longer restates docstring content. |
| Line-count | `git diff --stat` shows net reduction across the 4 touched files.  |
| Regression | Re-walk `/problem`, `/build`, `repair-escalation` flows to confirm every action an agent takes is unchanged. |

## Acceptance Criteria

- `problem.md` Phase 1.5 / dependency-check point to docstrings, don't restate them.
- `harness-reference.md` "Critic findings file" holds the full append+commit detail once.
- All 5 call sites reference it instead of repeating the block.
- `git diff --stat` shows net line reduction on the 4 touched files.
- No `.py` file, append format, commit convention, or control flow changes.

## Open Questions

None — scope is fixed by the ticket title and confirmed against current file contents.

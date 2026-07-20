# Requirements

**Ticket**: 0068
**Title**: Slim deliver-ticket.md: move merge/archive/learnings mechanics behind ticket.py

## Functional Requirements

1. `ticket.py` must expose `deliver-commit`/`deliver-publish` CLI subcommands
   (split from `deliver_squash()` so Step 4b's smoke test can gate between
   them): `deliver-commit` must squash-merge+archive+commit (JSON
   `pre_merge_sha`/`merge_commit_sha`/subject); `deliver-publish` must push,
   then only on success remove worktree+branch.
2. `deliver-publish` must raise and leave worktree+branch intact on a
   rejected push. A unit test must assert `deliver-commit` alone leaves
   worktree/branch present, unpushed (the gate invariant). `deliver_squash()`
   must stay callable, composing the two.
3. `deliver_squash_batch()`'s per-branch cleanup must reuse a helper shared
   with `deliver-publish`, removing the duplicate git-cleanup code.
4. `deliver-ticket.md` Step 4/4c must call the new CLI instead of inlining raw
   git; `test_0003_squash_delivery_docs.py`/`test_0019_deliver_smoke.py` must
   be updated to assert the new CLI-call text.
5. A new `learnings.py` must provide `parse_findings(text, source_kind,
   ticket_number, today)` (gate/critic walks, sanitize, severity/cap-at-5),
   standalone `sanitize_pattern(message)`, `dedupe_candidates()`, and
   `append_learnings()`. Both `/deliver` and `/harvest-learnings` must call
   these in place of `candidate-learnings-flow.md`'s prose.
6. `sanitize_pattern`'s directive-strip must be deterministic: it must strip
   any sentence containing a token (lowercased, depunctuated) anywhere in it
   from `{claude, assistant, ignore, disregard, system, now}`, or the phrase
   `you must` — never an open "when in doubt" judgment call.
7. `append_learnings()`'s stub header must be one Python constant; `/init`
   must create the stub by calling `learnings.py`, not by hand-authoring the
   header text. All functions must be CLI-reachable; the flow docs must
   retain only the lead's accept/reject exchange.

## Non-Functional Requirements

1. No behavior change: mechanics and sanitize/dedup/cap (incl. 120-char cap)
   output must stay identical to today for `/deliver` and `/harvest-learnings`.
2. `sanitize_pattern` must never let a `|`, control char, or stripped
   directive reach `pattern`; subprocess calls must use argument lists.

## Test Strategy

| Type | Rationale |
|------|-----------|
| Unit | commit/publish split + gate invariant + push-rejection; batch cleanup reuse; `parse_findings`/`sanitize_pattern`; `dedupe_candidates`; `append_learnings` |
| Integration | `deliver_squash()`/`_batch()` still one commit/ticket end-to-end (`test_ticket_module.py`, `test_batch_delivery.py`) |

## Acceptance Criteria

- `deliver-commit`/`deliver-publish` exist, unit tested incl. gate invariant;
  updated `deliver_squash()`/batch/doc tests pass.
- `learnings.py` functions exist, unit tested, CLI-invoked from `/deliver` and
  `/harvest-learnings`; flow docs keep only the lead exchange.
- Full `pytest` suite (existing, updated, new) passes.

## Open Questions

None.

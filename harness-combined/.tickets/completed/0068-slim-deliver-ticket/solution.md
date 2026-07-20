# Solution

**Ticket**: 0068
**Title**: Slim deliver-ticket.md: move merge/archive/learnings mechanics behind ticket.py

## Approach

Split `deliver_squash()` into `deliver-commit`/`deliver-publish` CLI
subcommands so Step 4b's smoke test can gate between them; `deliver_squash()`
and `deliver_squash_batch()`'s per-branch cleanup both compose a shared
`_remove_worktree_and_branch()` helper. Add `learnings.py` with
`sanitize_pattern` (a deterministic directive-strip rule, not "when in
doubt"), `parse_findings`, `dedupe_candidates`, `append_learnings`, exposed
via a thin CLI and used by **both** `/deliver` and `/harvest-learnings`
(replacing `candidate-learnings-flow.md`'s prose at both call sites). Update
`deliver-ticket.md`, `harvest-learnings.md`, `commands/init.md`, and
`harness-reference.md` to call these instead of re-deriving the logic.

## Components

| Component | Responsibility | Interface |
|---|---|---|
| `ticket.py::deliver_commit()` | squash-merge, fold archive, commit | `(repo, branch, slug, title) -> DeliverCommitResult` |
| `ticket.py::deliver_publish()` | push, then cleanup via shared helper | `(repo, branch, slug) -> None`, raises on push rejection |
| `ticket.py::_remove_worktree_and_branch()` | worktree remove + branch -D | shared by `deliver_publish` and `deliver_squash_batch` |
| `ticket.py::deliver_squash()` | existing single-call API | now `deliver_commit()` + `deliver_publish()` |
| CLI `deliver-commit`/`deliver-publish` | flow-doc entry points | JSON / plain status on stdout |
| `learnings.py::sanitize_pattern()` | deterministic directive-strip + char/`\|`/length rules | `(message) -> str \| None` |
| `learnings.py::parse_findings()` | gate+critic parsing, prioritize, cap | `(text, source_kind, ticket_number, today) -> list[dict]` |
| `learnings.py::dedupe_candidates()` / `append_learnings()` | dedup vs existing; stub-create + append | as before; header is a module constant |
| CLI `learnings.py candidates`/`dedupe`/`append`/`sanitize` | flow-doc entry points; `candidates` wraps `parse_findings` (gate/critic shape), `dedupe` takes pre-parsed records so `/harvest-learnings`'s BM25 output can reuse it directly | JSON in/out |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Two-phase split, not a callback param | Each phase independently testable/CLI-invocable, mirrors `claim()`/`set_status()`'s shape. |
| New `learnings.py`, not folded into `ticket.py` | Distinct concern (text sanitization) with its own test surface. |
| `sanitize_pattern` extracted as its own function | Lets `/harvest-learnings` reuse the identical trust-boundary logic instead of a second prose copy. |
| Fixed keyword set, token-scoped (not sentence-initial-only) | Prose's "when in doubt" is unauditable; a named set scanned across the whole sentence is testable and has no positional blind spot. |
| Interactive accept/reject stays in flow docs | Requires lead judgment — the one piece kept out of Python. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1/2 | Unit | `deliver-commit` alone leaves worktree/branch present and unpushed (gate invariant); `deliver-publish` cleans up on success, raises + leaves intact on rejection |
| FR-3 | Integration | `deliver_squash()`/`deliver_squash_batch()` still one commit/ticket end-to-end; batch cleanup calls the shared helper (existing `test_ticket_module.py`, `test_batch_delivery.py`) |
| FR-4 | Doc | `test_0003_squash_delivery_docs.py`/`test_0019_deliver_smoke.py` updated to assert CLI-call text |
| FR-5/6 | Unit | `sanitize_pattern` token-scoped keyword-set cases (each of `claude/assistant/ignore/disregard/system/now/you must`, mid-sentence placement), `|`/control-char/120-cap rules; `parse_findings` gate+critic tolerant-skip and cap-at-5 |
| FR-7 | Unit | `dedupe_candidates` (3- and 4-field lines); `append_learnings` stub header matches the shared constant |
| NFR-1 | Regression | Full existing `pytest` suite green |

## Tradeoffs

- **Extended scope to `/harvest-learnings`** rather than deferring it: the critic flagged that leaving it on the prose path would recreate the exact drift/injection risk this ticket exists to close, and `sanitize_pattern`/`dedupe_candidates`/`append_learnings` were already going to be built — reuse is near-zero marginal cost.
- **Accepting**: a few more CLI subcommands and one more touched file (`harvest-learnings.md`) increase this ticket's surface — mitigated by every mechanic staying behind the existing single-call wrappers, so no other caller changes.

## Risks

- Byte-for-byte sanitizer parity is the main risk — mitigated by porting Step 3's rules in order and testing each against the fixed keyword set now specified in requirements.md.
- Step 4b (out of scope) reads `pre_merge_sha`/`merge_commit_sha` as shell vars; the flow doc must extract them from `deliver-commit`'s JSON (e.g. `jq -r`) using the same field names — noted so it isn't improvised at build time.

## Implementation Order

1. `ticket.py`: extract `deliver_commit()`/`deliver_publish()`/`_remove_worktree_and_branch()`; wire `deliver_squash()`/`deliver_squash_batch()` to reuse them; add CLI subcommands; unit tests incl. gate invariant.
2. `learnings.py`: `sanitize_pattern()`, `parse_findings()`, `dedupe_candidates()`, `append_learnings()` + CLI; unit tests against the fixed keyword set and sanitization rules.
3. Update `test_0003_squash_delivery_docs.py`/`test_0019_deliver_smoke.py` to the new CLI-call text.
4. Update `deliver-ticket.md` Step 4/4c/5, `harvest-learnings.md`, and `commands/init.md`'s stub-creation to call the new CLI; update `harness-reference.md`; run full suite.

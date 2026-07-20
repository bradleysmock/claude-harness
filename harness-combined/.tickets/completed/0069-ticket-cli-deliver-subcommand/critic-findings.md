## Round 1 — 2026-07-19

# Critic Report — Ticket 0069 (Ticket CLI deliver subcommand)

**Phase:** code · **Round:** 1
**Panels active:** Core, Python, Testing Strategy (files in scope: `ticket.py`, `tests/test_0069_ticket_cli_deliver.py`)
**Gate findings:** none present at `.tickets/0069-ticket-cli-deliver-subcommand/gate-findings.md` (file does not exist)

## Requirements coverage (Step 2.5)

All six FRs and both NFRs/ACs are implemented and covered by a corresponding test:

- FR-1 (no `--push`, positional-only) — `ticket.py:960-964`; exercised implicitly by every test that omits the flag.
- FR-2 (`_resolve_claim` + `_read_ticket_docs`, explicit `FileNotFoundError` on missing `status.md`) — `ticket.py:966-972`; `test_deliver_cli_missing_status_md_is_file_not_found` (`tests/test_0069_ticket_cli_deliver.py:58-74`).
- FR-3 (`deliver_squash(repo, branch, slug, title)`, print returned subject) — `ticket.py:981`; `test_deliver_cli_happy_path_calls_deliver_squash` (`tests/test_0069_ticket_cli_deliver.py:33-55`).
- FR-4 (non-`review-ready` → non-zero, no call) — `ticket.py:973-980`; `test_deliver_cli_wrong_status_does_not_deliver` (`tests/test_0069_ticket_cli_deliver.py:77-97`).
- FR-5 (`RuntimeError` caught, stderr, exit 1) — `ticket.py:983-985`; `test_deliver_cli_runtime_error_from_deliver_squash_is_caught` (`tests/test_0069_ticket_cli_deliver.py:116-135`).
- FR-6 (missing id → usage/exit 2; unresolvable id → exit 1) — `ticket.py:961-965`, `983-985`; `test_deliver_cli_missing_ticket_id_exits_2` and `test_deliver_cli_unresolvable_ident_is_caught` (`tests/test_0069_ticket_cli_deliver.py:22-30`, `100-113`).
- Integration test (`test_deliver_cli_integration_full_flow`, `tests/test_0069_ticket_cli_deliver.py:138-195`) exercises the real `claim` → `review-ready` → `ticket.py deliver` path against a git fixture, asserting the squash commit, `completed/<slug>/status.md == done`, and the `delivered` ledger event — matches the Test Plan's Integration row exactly.

No missing implementation, no missing test for any stated requirement.

## Solution-alignment (Step 2.5)

Matches `solution.md` precisely: reuses `_resolve_claim`/`_read_ticket_docs` rather than a new resolver, no `--push` flag, single combined `except (FileNotFoundError, RuntimeError)`, `deliver_squash` untouched, `deliver-batch` untouched. The `_parse_status_lines` extraction (`ticket.py:83-93`) is a clean, backward-compatible refactor — verified every other `parse_status(...)` call site (`ticket.py:171,866,888,925`; `tests/test_ticket_module.py`; `tests/test_harness_tickets_branch.py:209`) is unaffected. No unjustified deviation found.

## Findings

**MINOR** · Core / Dimension 5 (Code Smells — Duplication), Beck rule 3 · `ticket.py:968-969` vs `ticket.py:698,738`
The branch/title fallback-resolution one-liners — `record.get("branch", f"ticket/{full_slug}")` and `record.get("title", full_slug)` — are now duplicated verbatim between the new `deliver` case and `_terminate` (used by `cancel`/`abandon`). This is duplication of *knowledge* (the same "ledger record may lack these fields, fall back to the conventional name" rule), not just literal text — if the fallback convention ever changes, one site can be missed. Fix: extract a small helper, e.g. `_branch_of(record, full_slug) -> str` / `_title_of(record, full_slug) -> str`, or a single `_resolve_branch_and_title(record, full_slug) -> tuple[str, str]`, and call it from both `deliver` and `_terminate`/`reopen`.

**OBS** · Core / Dimension 6 (Hyrum's Law / API surface), CLI-argument convention · `ticket.py:961`
The positional-arg filter (`[a for a in argv[1:] if not a.startswith("--")]`) silently drops any `--flag` the caller passes (e.g. `ticket.py deliver 0069-thing --push`) rather than rejecting an unrecognized flag. Since FR-1 deliberately omits `--push` support, a caller migrating from the old `python3 -c` invocation or copying the `claim`/`cancel` invocation shape and habitually adding `--push` gets silent no-op behavior instead of an error. This is a pre-existing systemic pattern shared by `deliver-batch`, `claim`, `cancel`/`abandon`/`reopen` (all use the same filter-not-validate convention), so it is not a regression introduced by this ticket — logged as an observation only, not a blocker for this diff.

**OBS** · Testing Strategy / Dimension 22 (seam choice) · `tests/test_0069_ticket_cli_deliver.py:33-135`
The five happy/error-path unit tests monkeypatch `_resolve_claim`, `_read_ticket_docs`, and `deliver_squash` — internal seams within the same module rather than the true external boundary (git/filesystem). This is a deliberate, ticket-sanctioned choice (per `problem.md`'s stated gap: `deliver_squash` already has unit coverage; this ticket's job is proving the *dispatch* routes correctly) and is complemented by the one full-fixture integration test that exercises the real boundary end-to-end. Noting as a legitimate Feathers-style "test at a chosen seam" rather than a Dodds-style "mocking at an internal seam" defect, since the plan and its rationale are explicit.

No BLOCKER or MAJOR findings.

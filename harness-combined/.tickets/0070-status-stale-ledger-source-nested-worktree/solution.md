# Solution

**Ticket**: 0070
**Title**: Status/stale ledger-sourced ticket discovery + nesting-aware worktree join

## Approach

Add `_project_offset(repo)` (git top-level to `repo`, empty for a flat repo,
`RuntimeError` on failure) and one shared helper on top of it,
`_worktree_ticket_dir(repo, worktree, slug)`, that every worktree/ticket-dir
path construction goes through — `claim`'s `_create_branch_and_worktree`
(stub write, `git add` pathspec, and idempotent-resume check, all three),
`list_tickets`, `reopen`, and `_read_ticket_docs` (round 2 found the latter two
reproduce claim's exact bug). One helper, four call sites, instead of four
ad-hoc re-derivations. Extend `list_tickets()`'s output with `updated`. Give
`status/SKILL.md` and `stale/SKILL.md` an embedded, deterministic `list-json`
enumeration (matching `ticket-list.md`'s pattern, not free-form prose),
reconciling their already-drifted "keep in sync" block into one byte-identical
version, test-verified rather than review-verified.

## Components

| Component | Responsibility |
|-----------|----------------|
| `ticket.py::_project_offset(repo)` | `git rev-parse --show-toplevel`; `Path(repo).relative_to(toplevel)` or `Path(".")`; wraps `relative_to`'s `ValueError` in `RuntimeError` matching `git()`'s diagnostic shape. |
| `ticket.py::_worktree_ticket_dir(repo, worktree, slug)` | `worktree / _project_offset(repo) / ".tickets" / slug`. The single join point every call site below uses — Parnas information hiding, closing the round-2 gap where fixing one site (claim) left three others (`git add` pathspec, `reopen`, `_read_ticket_docs`) on the old, wrong path. |
| `ticket.py::_create_branch_and_worktree` | `ticket_dir = _worktree_ticket_dir(...)`; the `git add` pathspec derives from `ticket_dir.relative_to(worktree)` (no more hardcoded `.tickets/{slug}/`); the resume-idempotency check probes the same corrected path. |
| `ticket.py::list_tickets` | `offset = _project_offset(repo)` once, before the per-ticket loop (NFR-2); per ticket, try the corrected path via the helper, fall back to the pre-fix path when absent. Output dict gains `"updated"`. |
| `ticket.py::reopen`, `ticket.py::_read_ticket_docs` | Both switch their `ticket_dir`/`worktree_dir` construction to the shared helper — closing round 2's BLOCKER (`reopen` silently corrupts a nested repo the same way `claim` did) and MAJOR (`_read_ticket_docs`'s "prefer live worktree" branch is dead code in a nested repo, falling through to `git show` unnoticed). |
| `skills/status/SKILL.md` Step 1, `skills/stale/SKILL.md` shared block | Both call `ticket.py list-json` as an embedded, argument-list subprocess (never a shell string) — primary source, `.tickets/*` scan only as an unreachable-engine fallback. Byte-identical shared block, checked by a marker-delimited equality test (round 2 MINOR). |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `git rev-parse --show-toplevel`, not `.harness/config.py` `PROJECT_ROOT` | Zero-config; no config file exists in this repo today. |
| One shared helper, not four independent fixes | Round 2 found a fix applied only at claim's stub left 3 other sites (its own `git add`, `reopen`, `_read_ticket_docs`) broken — a single join point removes that class of miss entirely. |
| Fallback-to-pre-fix-path in reads, not a hard cutover | All 8 live legacy worktrees verified already correct; the fallback is forward-looking insurance, not a known need. |
| `list-json` primary + fallback-on-unreachable, not `ticket-list.md`'s scan-wins-on-conflict merge | Deliberate simplification, not a literal mirror: `list-json` now carries `updated` directly, so there's no richer field left for a local scan to win on. |
| Embed the union as a literal script, not prose | This repo's own `## LLM/Python Boundary` rule: deterministic merge logic belongs in Python; also makes it unit-testable (round 1 finding). |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1, FR-2 | Unit | Offset: flat → `Path(".")`; nested fixture → correct; outside `toplevel` → `RuntimeError`. |
| FR-3, FR-5 | Unit | Shared helper drives `claim`/`reopen`/`_read_ticket_docs`/`list_tickets` identically on a nested fixture — one assertion per site, same helper. |
| FR-4 | Unit | `list_tickets()`: corrected-path read, pre-fix fallback, single `git()` call across N tickets. |
| FR-7 | Unit | `list_tickets()` output includes `updated` matching the fixture's `status.md`. |
| FR-8 | Unit | Embedded union script: ledger-primary, scan-fallback-only; byte-equality check of the two SKILL.md files' shared block. |
| FR-9 | — | Covered by composition of FR-3/FR-4/FR-8's tests together — no separate end-to-end test. |
| NFR-1 | Regression | `tests/test_ticket_module.py` passes unmodified. |

## Tradeoffs

- **Chose a relative-offset join over relocating `.worktrees/` to the git root because**: smaller, localized change.
- **Chose one shared helper over four site-local fixes because**: round 2 directly demonstrated the site-local approach misses call sites on re-review.
- **Accepting risk of**: a fifth, still-undiscovered call site with this assumption; problem.md scopes an audit as follow-up if found.

## Risks

- `reopen()`/`_read_ticket_docs` were live-reproducible bugs, not hypothetical — verified against current `ticket.py` lines 876, 977-991 this session.
- `git rev-parse --show-toplevel` failing outside a git repo already raises via `git()`'s existing `RuntimeError`; no new failure mode.

## Implementation Order

1. `_project_offset` + `_worktree_ticket_dir` + unit tests (flat/nested/outside-ancestry).
2. Fix `_create_branch_and_worktree` (stub + `git add` + resume check) via the helper; nested-fixture test.
3. Fix `reopen()` and `_read_ticket_docs()` via the same helper; nested-fixture tests for each.
4. Fix `list_tickets()`'s read (hoisted offset, fallback, `updated` field); test corrected-path, fallback, call-count.
5. Port the embedded `list-json` script into `status/SKILL.md` Step 1 and `stale/SKILL.md`'s shared block; byte-equality test between the two.
6. Run full `tests/test_ticket_module.py` to confirm no flat-repo regression.

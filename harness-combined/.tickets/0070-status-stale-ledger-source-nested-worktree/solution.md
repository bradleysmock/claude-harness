# Solution

**Ticket**: 0070
**Title**: Status/stale ledger-sourced ticket discovery + nesting-aware worktree join

## Approach

Add one pure helper, `_project_offset(repo)`, computing `repo`'s path relative
to the git top-level once per invocation (empty for a flat repo, `RuntimeError`
on failure — never a bare exception). Apply it everywhere `claim()` touches a
new worktree's ticket dir (stub write, `git add` pathspec, and the idempotent
resume check — all three, not just the write) and in `list_tickets()`'s
worktree-status read (offset hoisted above its loop, with a pre-fix-path
fallback for safety). Extend `list_tickets()`'s output with `updated` so
`list-json` is self-sufficient. Then give `status/SKILL.md` and `stale/SKILL.md`
an embedded, deterministic `list-json`-primary enumeration (matching
`ticket-list.md`'s pattern, not free-form prose), reconciling the two files'
already-drifted "keep in sync" block into one byte-identical version.

## Components

| Component | Responsibility |
|-----------|----------------|
| `ticket.py::_project_offset(repo)` | `git rev-parse --show-toplevel`; return `Path(repo).relative_to(toplevel)` or `Path(".")`. Wraps `relative_to`'s `ValueError` in `RuntimeError` with the same diagnostic shape as `git()`'s errors. |
| `ticket.py::_create_branch_and_worktree` | `offset = _project_offset(repo)`; `ticket_dir = worktree / offset / ".tickets" / full_slug`. The existing `git(worktree, "add", "--", f".tickets/{full_slug}/")` pathspec and the `(ticket_dir / "status.md").exists()` resume check both move to the same offset-corrected path — all three consistently, closing the gap round-1 review found (stub fixed, `git add` and resume check left stale). |
| `ticket.py::list_tickets` | `offset = _project_offset(repo)` computed once before the `for num in sorted(claims):` loop (not per-ticket — NFR-2). Per ticket: try `repo/.worktrees/<full>/<offset>/.tickets/<full>/status.md`; if absent, fall back to the pre-fix `repo/.worktrees/<full>/.tickets/<full>/status.md` (belt-and-suspenders — verified unneeded for the 8 live legacy worktrees this session, kept for forward safety). Output dict gains `"updated": fields.get("updated", "")`. |
| `skills/status/SKILL.md` Step 1, `skills/stale/SKILL.md` shared block | Both call `ticket.py list-json` as an embedded Python script (subprocess, argument-list, never a shell string — matching `ticket-list.md`'s `ledger_rows()`), primary source; fall back to the legacy `.tickets/*` scan only when the engine is unreachable (no CLAUDE_PLUGIN_ROOT / missing ticket.py / non-zero exit / bad JSON). Replaces `stale/SKILL.md`'s current ambiguous "scan first, ledger as fallback" wording with the correct ledger-primary contract; both files end byte-identical in this block. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `git rev-parse --show-toplevel`, not `.harness/config.py` `PROJECT_ROOT` | Zero-config; works today (no config file exists in this repo). |
| Fix at `ticket.py`'s path-join + `list-json` schema, once | `list-json`, `/status`, `/stale`, `/ticket-list` (future) all inherit it. |
| Offset-correct all three of stub/`git add`/resume-check together | Round-1 review: fixing only the stub write leaves `claim()` crashing on `git add` and orphaning stubs on resume. |
| Fallback-to-pre-fix-path in the read, not a hard cutover | Empirically all live legacy worktrees are already correct, but a silent read regression on an unverified future worktree is worse than one extra `exists()` check. |
| Embed the union as a literal script in both SKILL.md files, not prose | This repo's own `## LLM/Python Boundary` rule (0053): deterministic merge logic belongs in Python, not model-executed prose — also makes FR-7 testable. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1, FR-4 | Unit | Offset: flat → `Path(".")`; nested fixture → correct offset; `repo` outside `toplevel` → `RuntimeError`. |
| FR-2 | Unit | `claim()` on nested fixture: stub, `git add` pathspec, and resume-idempotency check all target the corrected path; resume never duplicates. |
| FR-3 | Unit | `list_tickets()`: reads corrected path; falls back to pre-fix path when corrected is absent; single `git()` call across N tickets. |
| FR-5 | Unit | `list_tickets()` output includes `updated` matching the worktree's `status.md`. |
| FR-6 | Unit | Embedded union script in both SKILL.md files: ledger-primary, scan-fallback-only, unit-tested like `ticket-list.md`'s `ledger_rows()`/`main()`. |
| NFR-1 | Regression | `tests/test_ticket_module.py` passes unmodified. |

## Tradeoffs

- **Chose a relative-offset join over relocating `.worktrees/` to the git root because**: smaller, localized change; doesn't touch every flow's literal path references.
- **Chose embedded scripts over porting `ticket-list.md`'s logic by reference/import because**: `SKILL.md` files are self-contained prose+script documents by convention here; duplication is accepted (same tradeoff `ticket-list.md` itself already made).
- **Accepting risk of**: an undiscovered third call site with the same worktree-root assumption; scoped out in problem.md, flagged for a follow-up audit if found.

## Risks

- Legacy worktrees (0053–0068): verified this session, all 8 still-live ones are
  already at the corrected path — the read-side fallback covers any missed case.
- `git rev-parse --show-toplevel` failing outside a git repo — already raises via
  `git()`'s existing `RuntimeError`; no new failure mode.

## Implementation Order

1. `_project_offset` + `RuntimeError` wrapping + unit tests (flat/nested/outside-ancestry).
2. Fix `_create_branch_and_worktree` (stub + `git add` + resume check together); test against nested fixture.
3. Fix `list_tickets()`'s read (hoisted offset, fallback, `updated` field); test corrected-path, fallback, and call-count.
4. Port the embedded `list-json`-union script into `status/SKILL.md` Step 1.
5. Reconcile `stale/SKILL.md`'s shared block to the same script, byte-identical to `status/SKILL.md`'s.
6. Run full `tests/test_ticket_module.py` to confirm no flat-repo regression.

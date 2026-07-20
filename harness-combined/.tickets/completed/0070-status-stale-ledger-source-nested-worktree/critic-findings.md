## Round 1 — 2026-07-20

## Critic Report — Round 1 (code review, full)

**Ticket:** 0070-status-stale-ledger-source-nested-worktree
**Panels active:** Core (always active), Python (`context/panels/python.md` — `ticket.py`, `tests/test_ticket_module.py`, `tests/test_0070_status_stale_ledger_source.py` match `**/*.py`), Testing Strategy (`context/panels/testing.md` — both test files match `**/tests/**`). Candidates: none disposed as relevant (no manifest/dep/content triggers fired for HTTP, security-specific, or infra panels in this diff). Skipped: none — all listed files resolved under `--root`.

Step 2 (gate-findings.md): none exists for this ticket per the brief; skipped as instructed.

Step 2.5 (requirements coverage / solution alignment / weakened tests) applied alongside panel dimensions below.

---

**BLOCKER** · Core / Dimension 6 (Parnas information hiding) + Requirements coverage · `ticket.py:1181-1184` <!-- harness-finding-key :None:BLOCKER:Core / Dimension 6 (Parnas information hiding) + Requirements coverage -->

FR-1 explicitly names `list_tickets` as one of the four call sites that must use the shared join-point helper: "every site building a worktree-relative ticket-dir path uses it — `_create_branch_and_worktree`, `list_tickets`, `reopen`, `_read_ticket_docs`." `_create_branch_and_worktree` (line 458), `reopen` (line 1080), and `_read_ticket_docs` (line 977) all call `_worktree_ticket_dir(...)`. `list_tickets` does not — it re-derives the identical expression by hand:
```python
corrected_status = worktree / offset / ".tickets" / full / "status.md"
```
This is functionally equivalent today only because the author manually copied `_worktree_ticket_dir`'s formula (`worktree / _project_offset(repo) / ".tickets" / slug`, `ticket.py:431`) rather than calling it — precisely the "four ad-hoc re-derivations" failure mode solution.md names as the reason for introducing one shared helper ("round 2 found a fix applied only at claim's stub left 3 other sites... broken — a single join point removes that class of miss entirely"). The docstring at `ticket.py:412-413` asserts "the single join point every call site below goes through instead of re-deriving this by hand" — that claim is false for `list_tickets`, making it a stale/inaccurate comment as well as a duplication-of-knowledge defect (Beck's "no duplication" — not just literal copy-paste, but duplication of the *join logic itself*). The root cause is that `_worktree_ticket_dir(repo, worktree, slug)` recomputes `_project_offset(repo)` internally on every call, so calling it per-ticket inside `list_tickets`'s loop would violate NFR-2 (offset computed once) — but the fix should have been to make the abstraction deep enough to serve this caller (e.g., split into a pure `_join_ticket_dir(worktree, offset, slug)` that both `_worktree_ticket_dir` and `list_tickets` call), not to silently drop FR-1 compliance for this one site while leaving the docstring's claim uncorrected. No test (`test_list_tickets_nested_reads_corrected_worktree_status`, `test_list_tickets_calls_project_offset_once`) checks that `list_tickets` actually routes through the named helper — both only assert on output, so a future change to `_worktree_ticket_dir`'s formula would silently diverge here undetected.

---

**BLOCKER** · Core / Dimension 4 (documentation accuracy) + Requirements coverage · `skills/stale/SKILL.md:61-64` (byte-identical text also at `skills/status/SKILL.md:51-54`) <!-- harness-finding-key :None:BLOCKER:Core / Dimension 4 (documentation accuracy) + Requirements coverage -->

FR-8 and solution.md's Components table both require the shared block's enumeration to be "`list-json` ... primary source, `.tickets/*` scan only as an unreachable-engine fallback" — i.e., the scan runs only when `list-json` itself errors. The shipped text instead reads:

> "Scan `.tickets/*/status.md` — one level deep only — for any local/legacy copies... If `.tickets/` does not exist or contains no `status.md` files, **fall back to the ledger enumeration above**..."

Read literally, this makes the filesystem scan primary and the ledger the fallback (triggered when the scan target is empty/missing) — the exact inverse of FR-8's stated precedence, and a direct reintroduction of the bug problem.md exists to fix: "still enumerate via a raw `.tickets/*` scan on `main`; `claim()` writes nothing there under the ledger model, so a new ticket is invisible." Under this literal reading, any repo with at least one legacy `.tickets/<slug>/status.md` on `main` would never reach the "fall back to the ledger" branch, so a newly-ledger-claimed ticket (living only on its branch) would be silently dropped from both `/status`'s stale-summary sub-procedure and all of `/stale`'s output — reproducing the invisibility bug this ticket was written to close. This also creates an internal contradiction within `status/SKILL.md` itself: Step 1's own top-level prose (lines 12-16) correctly states ledger-primary/scan-only-on-error, while the shared block reused two sections later for the stale-count sub-feature (and the entirety of `stale/SKILL.md`'s Step 2) states the opposite precedence. None of the new tests in `tests/test_0070_status_stale_ledger_source.py` check this precedence — `test_shared_blocks_are_byte_identical` only checks the two files match each other, and `test_status_step1_enumerates_via_list_json` scans the substring "Fallback" anywhere across the *entire* Step 1 section (which passes only because Step 1's own separate, correctly-worded prose contains it) — so this inversion is untested per solution.md's own Test Plan row ("FR-8 | Unit | Embedded union script: ledger-primary, scan-fallback-only").

---

No further findings within the panels applied (Python, Testing, Core) beyond the two above; the remainder of `ticket.py`'s new helpers (`_project_offset`, `_create_branch_and_worktree`, `reopen`, `_read_ticket_docs` changes) and the new test coverage for the offset/nesting logic itself are sound and match FR-2/3/5/6/7 and their corresponding tests.


## Round 2 — 2026-07-20

## Critic Report — Round 2 (code review, incremental)

**Ticket:** 0070-status-stale-ledger-source-nested-worktree

**Panels active:** Core (always active), Python, Testing Strategy. Candidates: none. Skipped: none.

Step 2 (gate-findings.md): confirmed absent per the caller's note (pre-existing whole-tree mypy collision, unrelated to this diff) — skipped.

Step 2.5: requirements coverage and solution-alignment skipped per incremental-round instructions. Weakened/deleted-tests check applied against `solution.md`'s Test Plan — no test was removed, skipped, or had an assertion loosened; two tests were added this round, both strengthening coverage. No new suppression pragmas found in `ticket.py`.

**Pass 1 — Prior-finding classification:**

Both round-1 BLOCKER findings are **fixed**.

1. `ticket.py:1181-1184` (Core / Dimension 6 + Requirements coverage) — **fixed**. `_worktree_ticket_dir` is now split into a pure `_join_ticket_dir(worktree, offset, slug)` (`ticket.py:429-434`), which `list_tickets` now calls directly instead of re-deriving the join expression by hand, and which `_worktree_ticket_dir` itself calls. The stale docstring is corrected. A new test, `test_list_tickets_routes_through_join_ticket_dir`, monkeypatches `_join_ticket_dir` and asserts `list_tickets` actually calls it.

2. `skills/stale/SKILL.md:61-64` / `skills/status/SKILL.md:51-54` (Core / Dimension 4 + Requirements coverage) — **fixed**. The shared block now reads "Fallback (ledger unreachable only). If `ticket.py list-json` itself errors, fall back to scanning..." removing the prior scan-primary/ledger-as-fallback-on-empty misreading. Verified byte-identical between both files. A new test, `test_shared_block_is_ledger_primary_not_scan_primary`, asserts precedence ordering in the shared block.

**Pass 2 — New findings (touched files only):**

None.


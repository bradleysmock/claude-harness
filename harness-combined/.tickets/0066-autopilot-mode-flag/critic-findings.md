## Round 1 — 2026-07-20

## Critic Report — 0066-autopilot-mode-flag (code review, round 1)

**Active panels:** Core (always active) + Python (`mode_branch.py`, `tests/*.py`) + Testing (`tests/test_mode_branch.py`, `tests/test_0066_autopilot_mode_flag.py`). No other trigger in the SKILL.md table matches — the flow docs are markdown, not covered by any language/framework panel.

**Gate findings:** none exist for this ticket (documented pre-existing repo-wide mypy collision, unrelated to this change); full pytest suite passes per the task brief.

### Step 2.5 — Ticket-baseline checks

- **Requirements coverage:** FR-1 through FR-7 and NFR-1/NFR-2 each have a corresponding implementation and a passing content-verification or unit test (`tests/test_0066_autopilot_mode_flag.py`, `tests/test_mode_branch.py`). Verified by direct read of `context/flows/build-ticket.md:7,40-42,291-296,337-343,347-361` and `context/flows/autopilot-ticket.md:12-14`. `autopilot-batch.md` confirmed untouched (`grep MODE` → no matches) satisfying FR-7.
- **Alignment with `solution.md`:** implementation matches the documented approach exactly — one shared predicate (`mode_branch.py:16`), called by name at all three sites, preserved-wording verbatim at each `False` branch, `autopilot-ticket.md` shrunk to announcement/signal/delegation/Steps S-A-B. No unexplained deviation found.
- **Weakened or deleted tests:** none found. This ticket only adds `mode_branch.py`, `tests/test_mode_branch.py`, `tests/test_0066_autopilot_mode_flag.py`, and edits the two flow docs; no existing test file, assertion, or suppression pragma was touched.

### Findings

No BLOCKER or MAJOR findings.

**OBS** · Core / Dimension 6 (Design Principles, Beck's "fewest elements") · `mode_branch.py:13` <!-- harness-finding-key mode_branch.py:13:OBS:Core / Dimension 6 (Design Principles, Beck's "fewest elements") -->

`AUTOPILOT_MODE = "autopilot"` is exported at module scope but never imported or referenced anywhere outside its own use inside `is_autopilot_mode` (verified via `grep AUTOPILOT_MODE` across the worktree — only the two lines in `mode_branch.py` match). The flow docs and `autopilot-ticket.md` set the mode via the literal string `MODE=autopilot`, not the constant, so the export currently has no consumer. This mirrors `DRY_RUN_FLAG` in `dry_run.py` closely enough that it's a reasonable stylistic precedent match rather than a defect — logged for awareness only, no action needed.

### Non-findings worth noting (checked, no issue)

- The `write-spec-ticket.md:18` sub-flow's own unconditional "if BLOCK, stop" instruction, invoked from `build-ticket.md` Step 1 before the new `is_autopilot_mode(MODE)` branch overrides it — this override pattern predates this ticket and is unchanged by it; out of scope.
- `test_0066_autopilot_mode_flag.py:110-115`'s magic-number line-count assertion (`< 95`) is explained inline with a why-comment tying it to the AC's "shorter than current version" requirement — acceptable per Core Dimension 4.
- No stale cross-references to the removed "watch for" interception prose found elsewhere in the repo.

**Verdict:** Approve as-is.

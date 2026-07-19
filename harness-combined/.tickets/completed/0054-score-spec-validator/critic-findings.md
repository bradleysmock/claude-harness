## Round 1 — 2026-07-19

Panels active: Core (always) + Python (`.py` files in scope) + Testing (`tests/` directory in scope). No other trigger conditions (HTTP/API, Database, security-specific libraries, etc.) are met by `validators/score_spec.py`, `tests/test_0054_score_spec.py`, or the `context/score-spec.md` doc edit.

Step 2.5 (ticket-baseline) and panel-based review were both applied against `.tickets/0054-score-spec-validator/{problem,requirements,solution}.md`, `context/score-spec.md`, `validators/score_spec.py`, `tests/test_0054_score_spec.py`, and (for context) `gates/spec_remediate.py`.

### Findings

**BLOCKER — Core / Dimension 8 (McGraw: fail closed) + Step 2.5 requirements coverage (FR-7)** — `validators/score_spec.py:94-109`

`_spec_remediate = _load_spec_remediate()` runs at **module import time** (line 109), entirely outside `main()`'s `try`/`except` block (lines 325-336). `_load_spec_remediate()` does real file I/O and can raise `ImportError` (line 98, when `module_spec`/`module_spec.loader` is `None`), `OSError` (unreadable file), or `ValueError` (`_resolve_contained`'s containment check, line 85). None of these are caught anywhere before or during import — a failure here produces a raw Python traceback and the interpreter's default exit code 1, not the fail-closed exit 2 FR-7 mandates ("internal exceptions must exit 2... never a traceback-driven exit 1"). This is also the exact cross-environment seam NFR-1 flags as a concern ("works identically in repo and plugin cache") — the plugin-cache and repo layouts are exactly the scenario where this relative-path load is most likely to diverge. Additionally, even if this load were moved inside `main()`'s `try`, the current except tuple (`OSError, ValueError, LookupError, TypeError`) does not include `ImportError`, so the failure would still propagate uncaught. No test exercises a spec_remediate-load failure — `test_cli_unreadable_file_exits_2` only breaks `solution.md`'s read, not the sibling-module load.

**Fix:** Defer `_load_spec_remediate()` to be called lazily from inside `main()`'s existing `try` block (e.g., load once on first use and cache in a module-level variable, or call it as the first statement inside `main()`'s `try`), and add `ImportError` to the caught exception tuple.

---

**MAJOR — Core / Dimension 6 (Design Principles) + Python panel / Dimension 10** — `validators/score_spec.py:118-129` vs `:132-149`, `gates/spec_remediate.py:150-172`

Check 1 (`_check_fr_count`) deliberately does *not* reuse `spec_remediate`'s FR-parsing helpers — the inline comment at `score_spec.py:119-124` explains that `functional_requirement_numbers` "also matches indented numbered sub-items as if they were their own top-level FR." But checks 2 and 3 (`_check_imperative`, `_check_testplan`, lines 132-149) *do* reuse those same helpers (`nonimperative_fr_numbers`, `uncovered_fr_numbers`, `phantom_fr_numbers`), which are built on `_iter_fr_items` (`gates/spec_remediate.py:150-172`). `_iter_fr_items` matches `_FR_ITEM = re.compile(r"^\s*(\d+)\.\s+(.*)$")` with `\s*` permitting indentation — so a nested numbered sub-item like the one in the ticket's own fixture (`1. The system must do B.` → `   1. A nested clarifying sub-point`) is parsed as a *second, competing* "FR-1," overwriting/duplicating the number. This means for any ticket whose FR section contains a nested numbered sub-list — a pattern the ticket's own `test_fr_count_ignores_nfr_and_nested_sublist` fixture proves is anticipated and valid — checks 2 and 3 (both BLOCK-severity) can silently misattribute a sub-point's text to the wrong FR number, or produce spurious duplicate/incorrect FR-number sets in the coverage and imperative-language checks. This divergence is untested for checks 2/3 (only check 1's fixture uses nesting); solution.md's Tradeoffs section documents that checks 1-3 intentionally stay "behaviorally identical to Step S remediation by construction," but doesn't address that check 1's own top-level-only scoping creates an inconsistency the other two checks don't share.

**Fix:** Either scope checks 2/3 to top-level-only FR items as well (reusing the same top-level filter as check 1, then feeding only those numbers/text into the imperative/coverage logic), or add regression tests proving the nested-sublist case produces correct (not merely non-crashing) BLOCK/PASS results for checks 2 and 3.

---

**MINOR — Testing panel / Dimension 22 (Test Strategy & Suite Shape)** — `tests/test_0054_score_spec.py:264-320`, `validators/score_spec.py:209-211`

`_BARE_KEYWORD_RE` matches five distinct tokens (`TODO`, `TBD`, `FIXME`, `XXX`, `???`), but every placeholder fixture in the test file exercises only `TODO`. `TBD`, `FIXME`, `XXX`, and `???` have no dedicated test, so a regression that breaks the alternation for any of those four tokens (e.g., an accidental anchor change) would go undetected.

**Fix:** Add one parametrized or additional fixture covering the remaining four keyword variants.

---

**MINOR — Testing panel / Dimension 22 (Tests probing implementation loosely)** — `tests/test_0054_score_spec.py:552-557`

`test_doc_scopes_model_to_check_7_only` asserts `"only"` appears within an arbitrary 400-character window before/after the string `"check 7"` in the doc. This is a brittle proxy for "the doc scopes the model to check 7 only" — it would pass on unrelated prose containing "only" nearby, and would false-negative on a correctly-worded but differently-structured sentence. It doesn't verify semantic content, only lexical proximity.

**Fix:** Replace with a more targeted assertion, e.g. a regex anchored to the specific sentence pattern the doc uses ("model performs only check 7" or similar), rather than a 400-character window scan.

## Round 2 — 2026-07-19

Panels active: Core (always) + Python (`**/*.py` in scope) + Testing Strategy (`tests/**` in scope). No framework/HTTP/DB/security-specialty panels triggered — this is a stdlib-only CLI validator with no network, subprocess, template, or persistence surface.

Gate findings: none exist for this ticket (directory-mode gate fails-fast on pre-existing, unrelated import-order debt before reaching the new files' phases). New files independently verified clean (ruff/mypy/pytest — 35 tests); not re-verified by this round.

### Step 2.5 — Ticket-baseline checks

**Requirements coverage:** All 9 functional requirements and both non-functional requirements in `requirements.md` have a corresponding implementation and at least one passing test. Cross-checked FR-1 through FR-9 and NFR-1/NFR-2 against `validators/score_spec.py` and `tests/test_0054_score_spec.py` line by line — no gaps found. Test Plan table in `solution.md` is fully realized, with several bonus tests beyond the plan (e.g. `test_nested_sublist_weak_modal_attributed_to_owning_fr_not_colliding_number`, `test_nested_sublist_does_not_break_testplan_coverage`, `test_cli_spec_remediate_load_failure_exits_2_not_traceback`).

**Alignment with `solution.md`:** Architecture, component split, and tech choices match the solution document closely, including the deliberate `_top_level_fr_items` vs. `spec_remediate._iter_fr_items` divergence (documented at length in both the module docstring and solution.md's Tradeoffs section). All four score-spec.md wording pins are present. One minor deviation noted below (OBS).

**Weakened/deleted tests:** None found. No skips, no loosened assertions, no unexplained suppression pragmas anywhere in the diff.

### Findings

**MINOR — Core / Dimension 8 / McGraw (fail-closed)** — `validators/score_spec.py:381`

`main()`'s except clause is `except (OSError, ValueError, LookupError, TypeError, ImportError)`. FR-7 requires internal exceptions "must exit 2... never a traceback-driven exit 1." This is a fixed, non-exhaustive tuple: an exception type outside it (e.g. `AttributeError`, `KeyError`, `IndexError`) introduced by a future edit to this file or to `gates/spec_remediate.py` would propagate uncaught, producing a real traceback and exit code 1 — silently violating the "never exit 1 on an internal exception" guarantee. No currently-exercised code path triggers this today, so this is not exploitable now, but the fail-closed contract is not structurally guaranteed against regressions.

**Fix (not applied — MINOR, lead's call):** Either a closing `except Exception` fallback bucket (re-raising `KeyboardInterrupt`/`SystemExit`) or a code comment explicitly scoping the guarantee to "exceptions raised by this module's own code paths as currently written." Note: this repo's `pre_write_guard` hook blocks a bare `except Exception` write outright (see BLOCKER remediation in Round 1 → repair), so a broader catch here would need a narrower named tuple, not a bare `Exception`.

**OBS — Step 2.5 / solution.md alignment** — `validators/score_spec.py:381` vs. `solution.md:28`

`solution.md`'s Tech Choices table documents "`main()` catches `OSError`/`ValueError`"; the implementation catches a broader tuple (adds `LookupError, TypeError, ImportError`, added during Round-1 repair). The expansion strengthens rather than weakens the fail-closed guarantee; only the tech-choices table text is now stale.

**OBS — Core / Dimension 6 (Beck: no duplication)** — `validators/score_spec.py:172-198` vs. `gates/spec_remediate.py:150-172`

`_top_level_fr_items` duplicates the shape of `spec_remediate._iter_fr_items` with different indentation semantics. Deliberately chosen and justified (module docstring, solution.md Tradeoffs) — logged as a tradeoff, not an action item.

No BLOCKER or MAJOR findings. Fence-aware placeholder scanner, unclosed-fence toggle parity, inline-code masking, the top-level FR parser's nested-sublist handling, and the CLI's byte-exact report formatting were all traced by hand against their edge-case tests and found correct.

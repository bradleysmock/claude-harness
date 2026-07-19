# Solution

**Ticket**: 0054
**Title**: Score-spec Python validator: mechanical checks 1-6

## Approach

Add `validators/score_spec.py`, a stdlib-only CLI mirroring `standards_validator.py`:
a pure `score(requirements_text, solution_text)` seam plus `main()` that reads a
ticket directory, prints the header, six mechanical check lines, and verdict, and
exits 0/1/2 for PASS/WARN/BLOCK with all error paths mapped to exit 2 (fail closed).
Checks 1-3 reuse `gates/spec_remediate.py`; `context/score-spec.md` is updated so
consumers run the script for checks 1-6 and judge only check 7.

## Components

| Component | Responsibility |
|-----------|----------------|
| `validators/score_spec.py` | `CheckResult` dataclass, per-check functions, `score()`, CLI `main(argv)` with contained paths and fail-closed error mapping |
| `tests/test_0054_score_spec.py` | Unit fixtures per check via `score()`; CLI integration (report bytes, exit codes, error paths); RECIPE-label regression test |
| `context/score-spec.md` edit | Validator invocation for checks 1-6; check-7-only model role; composition rule (insert testability line above verdict, recompute); wording pins for check 1 (FR-section scope, top-level items), check 2 (weak-modal-only), check 5 (inline-code exemption), check 6 (section-scoped bullet count) |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Load `spec_remediate.py` via `importlib.util.spec_from_file_location` on the sibling `gates/` path | Direct behavioral reuse of `functional_requirement_numbers` / `nonimperative_fr_numbers` / `uncovered_fr_numbers` / `phantom_fr_numbers` (checks 1-3) with no `gates/__init__` execution (that init imports `models` and a tomli fallback); works identically in repo and plugin cache |
| Exit codes 0=PASS, 1=WARN, 2=BLOCK; errors also 2 | `main()` catches `OSError`/`ValueError` and exits 2 with stderr reason, so a crashed or artifact-less gate can never read as advisory WARN; argparse usage errors already exit 2 |
| Report on stdout, errors on stderr | The report block is the contract output consumers display verbatim |
| Fence-aware line scanner for check 5 | Toggle on backtick/tilde fences with info strings; unclosed fence content rescanned as unfenced (fail closed); inline single-backtick spans exempt, mirroring check 2's inline-code precedent |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | 2 FRs -> BLOCK; 3 FRs -> PASS; numbered NFRs outside the FR section not counted; nested numbered sub-list inside an FR not counted (wrapper filters to top-level, characterizing the `spec_remediate` edge) |
| FR-2        | Unit        | weak modal in FR -> BLOCK; weak modal inside inline code -> PASS; no-modal FR -> PASS |
| FR-3        | Unit        | FR missing from Test Plan -> BLOCK; phantom Test Plan FR -> BLOCK; combined `FR-5/9` cell parsed |
| FR-4        | Unit        | stub keyword outside fence -> BLOCK with line:column; inside backtick fence, tilde fence, or inline span -> PASS; after unclosed fence -> BLOCK; single-token bracket span not flagged; all-ellipsis row flagged |
| FR-5        | Unit        | missing Implementation Order -> WARN; 1 acceptance bullet -> WARN; bullets outside the section not counted; both present -> PASS |
| FR-6        | Integration | CLI on clean fixture: byte-exact header + 6 lines + verdict, exit 0; WARN fixture exit 1; BLOCK fixture exit 2 |
| FR-7        | Integration | missing `solution.md` -> exit 2, reason on stderr, no traceback; unreadable file -> exit 2; no-args usage error -> exit 2 |
| FR-8        | Unit        | `score()` called with plain strings returns per-check results; no tmp files involved |
| FR-9        | Integration | content assertions on `context/score-spec.md`: invocation named, check-7 scope, insert-above-verdict + recompute rule stated |

## Tradeoffs

- **Chose importlib file-load of `spec_remediate` over duplicated regexes because**:
  checks 1-3 stay behaviorally identical to Step S remediation by construction;
  the label regression test pins the remaining name-level coupling (`RECIPE` holds
  only the four BLOCK labels — the two WARN labels are pinned by the byte-exact
  report fixture instead).
- **Accepting risk of**: prose consumers ignoring the doc change; mitigated by
  stating the invocation as the required procedure inside score-spec.md's checks
  section itself.

## Risks

- Composition drift between validator output and the model-assembled final report.
  Mitigation: score-spec.md's edit is drafted (step 3) before `main()`'s printer is
  finalized (step 4), and the integration test asserts the byte-exact block.
- Doc-wording pins (checks 1, 2, 5) touch score-spec.md text other tickets cite.
  Mitigation: pins only resolve ambiguity in the validator's favor; severities,
  labels, and verdict rules are untouched.

## Implementation Order

1. Tests first: `tests/test_0054_score_spec.py` fixtures and assertions (TDD).
2. `validators/score_spec.py`: spec_remediate loader, per-check functions, `score()`.
3. Draft the `context/score-spec.md` edit: invocation, composition rule, wording pins.
4. CLI `main()`: args, contained paths, printer matching the drafted contract, exits.
5. Gate-exact ruff/mypy on new files; targeted pytest suite green.

# Solution

**Ticket**: 0053
**Title**: LLM/Python boundary rule in CLAUDE.md

## Approach

Add one hard-constraint section, `## LLM/Python Boundary`, to the shipped
CLAUDE.md between `## Code Generation Rules` and `## Reference`. It codifies the
existing de-facto split — deterministic authority in Python, judgment in the
model — as a citable rule: a two-column table, a decision test, a fail-closed
clause for missing helpers, and named precedents in `${CLAUDE_PLUGIN_ROOT}/`
form. A content-verification pytest locks presence, position, and anchor phrases.

## Components

| Component | Responsibility |
|-----------|----------------|
| `CLAUDE.md` § LLM/Python Boundary | Rule: Python owns pass/fail authority + exactness ops; model is judgment-only and never re-derives or overrides a Python verdict (may flag a suspected tool defect to the lead; verdict stands until the Python side changes). Fail-closed: a missing/erroring helper reports skipped/failed — the model never substitutes its judgment. Cites `${CLAUDE_PLUGIN_ROOT}/ticket.py`, `.../ticket_deps.py`, `.../ticket_templates.py`, `.../validators/standards_validator.py`, `.../gates/`. |
| `tests/test_0053_llm_python_boundary.py` | Reads CLAUDE.md; asserts: heading exactly once, indexed after `## Code Generation Rules` and before `## Reference`; the canonical anchors below, matched within the extracted section body only (same section-slicing pattern as `test_0038`'s `_section_from`); pre-existing `## ` headings present in original order; ≥3 cited paths — backticked `${CLAUDE_PLUGIN_ROOT}/…` tokens extracted from the new section only, prefix stripped — exist at repo root. |

## Canonical anchor phrases (test contract, fixed at design time)

| FR | Anchor (substring match) |
|----|--------------------------|
| FR-2 | `pass/fail authority` and `implemented in Python` |
| FR-3 | `exactness operations` |
| FR-4 | `judgment only` and `never re-derives or overrides` |
| FR-5 | `if two runs must agree on the answer, it belongs in Python` |
| FR-6 | `never substitutes its own judgment` |

Anchors are short substance-bearing fragments, not full sentences — the lead can
reword surrounding prose without breaking the test.

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Table + bullets, ≤25 lines | Matches adjacent Code Generation Rules hard-constraint style. |
| Content-verification pytest | Established markdown-deliverable pattern (cf. `tests/test_0038_stack_advisor_flow.py`). |
| `${CLAUDE_PLUGIN_ROOT}/` citation form | CLAUDE.md ships to user project roots; bare repo paths would name nonexistent files there. |
| Section-scoped path extraction | Prevents false pass from paths cited elsewhere in CLAUDE.md. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Heading occurs once; index after `## Code Generation Rules`, before `## Reference`. |
| FR-2 | Unit | Authority anchors present in section body (table above). |
| FR-3 | Unit | Exactness-ops anchor present in section body (table above). |
| FR-4 | Unit | Judgment-only + never-override anchors present in section body. |
| FR-5 | Unit | Decision-test sentence present in section body. |
| FR-6 | Unit | Fail-closed anchor present in section body (table above). |
| FR-7 | Unit | ≥3 section-scoped cited paths exist after prefix strip. |
| FR-8 | Unit | The test file itself is the deliverable; passes under tooled Python. |
| NFR-2 | Unit | Pre-existing headings present in original order (ongoing guard); byte-identity checked once via `git diff` at review. |

## Tradeoffs

- **Chose anchor phrases over full-text snapshot because**: pins substance, not bytes.
- **Chose CLAUDE.md-only scope over duplicating into harness-reference.md because**: one authority document; duplication drifts.
- **Accepting risk of**: rule being advisory for existing flows — current
  violations (e.g. model-applied checklists) are explicitly follow-up work.

## Risks

- Concurrent ticket editing CLAUDE.md would squash-conflict — standard
  rebase-before-deliver recipe mitigates.
- Over-broad reading could ban judgment rubrics feeding a verdict (score-spec) —
  wording scopes the rule to verdict authority and exact computation.

## Implementation Order

1. Write `tests/test_0053_llm_python_boundary.py` (red).
2. Insert the `## LLM/Python Boundary` section into CLAUDE.md (green).
3. Run gate-exact ruff on the test file; verify additive-only CLAUDE.md diff.

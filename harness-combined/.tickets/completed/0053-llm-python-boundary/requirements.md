# Requirements

**Ticket**: 0053
**Title**: LLM/Python boundary rule in CLAUDE.md

## Functional Requirements

1. CLAUDE.md must contain a new top-level section `## LLM/Python Boundary`,
   inserted between `## Code Generation Rules` and `## Reference`.
2. The section must state that pass/fail authority — gate verdicts, validator
   outcomes, score thresholds, structural checks — is implemented in Python
   invoked by commands/hooks, never rendered as model judgment.
3. The section must state that exactness operations — counting, line limits,
   parsing, ID/numbering, dependency-cycle detection, path containment — are
   implemented in Python, never eyeballed by the model.
4. The section must define the model's role as judgment-only (design, critique,
   repair strategy, remediation content) and state that the model must not
   re-derive or override a Python-computed verdict. Carve-out: the model is
   permitted to flag a suspected tool defect to the lead, but the verdict
   stands until the Python side is changed.
5. The section must include the decision test: "if two runs must agree on the
   answer, it belongs in Python."
6. The section must state the fail-closed rule: when a required Python helper
   is missing or errors, the check reports as skipped or failed — the model
   never substitutes its own judgment for the missing verdict (0043 precedent).
7. The section must cite ≥3 existing helpers using the shipped-file form
   `${CLAUDE_PLUGIN_ROOT}/<path>` (e.g. `ticket.py`, `ticket_deps.py`,
   `validators/standards_validator.py`), matching CLAUDE.md's convention.
8. A content-verification test `tests/test_0053_llm_python_boundary.py` must
   read CLAUDE.md and assert the heading, position, and the canonical anchor
   phrases enumerated in solution.md for FR-2..FR-6.

## Non-Functional Requirements

1. The inserted section is concise (≤ 25 lines) and matches the tone of the
   existing hard-constraint sections.
2. The change is purely additive. Byte-identity of other sections is verified
   once via `git diff` at review; the *ongoing* test guard is the weaker
   invariant "all pre-existing `## ` headings present in original order"
   (survives future legitimate section additions).
3. The new test file passes the gate-exact lint (`ruff --select E,F,W,I --ignore E501`).

## Test Strategy

| Type        | Rationale                                                        |
|-------------|------------------------------------------------------------------|
| Unit        | Content-verification pytest reads CLAUDE.md, asserts heading/position/anchor phrases (established pattern for markdown deliverables). |
| Integration | None — no runtime surface; the document is the deliverable.      |

## Acceptance Criteria

- `## LLM/Python Boundary` occurs exactly once, after `## Code Generation Rules`
  and before `## Reference`.
- `pytest tests/test_0053_llm_python_boundary.py` passes with the tooled Python.
- `git diff` on CLAUDE.md shows only the inserted block (additive-only).
- ≥3 cited helper paths (after stripping `${CLAUDE_PLUGIN_ROOT}/`) exist in the repo.

## Open Questions

None.

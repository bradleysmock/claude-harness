# Spec Coverage Map

**Ticket**: 0053-llm-python-boundary
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | CLAUDE.md must contain a new top-level section `## LLM/Python Boundary`, | 0053-llm-python-boundary-claude-md |
| FR-2 | FR | The section must state that pass/fail authority — gate verdicts, validator | 0053-llm-python-boundary-claude-md |
| FR-3 | FR | The section must state that exactness operations — counting, line limits, | 0053-llm-python-boundary-claude-md |
| FR-4 | FR | The section must define the model's role as judgment-only (design, critique, | 0053-llm-python-boundary-claude-md |
| FR-5 | FR | The section must include the decision test: "if two runs must agree on the | 0053-llm-python-boundary-claude-md |
| FR-6 | FR | The section must state the fail-closed rule: when a required Python helper | 0053-llm-python-boundary-claude-md |
| FR-7 | FR | The section must cite ≥3 existing helpers using the shipped-file form | 0053-llm-python-boundary-claude-md |
| FR-8 | FR | A content-verification test `tests/test_0053_llm_python_boundary.py` must | 0053-llm-python-boundary-claude-md |
| AC-1 | AC | `## LLM/Python Boundary` occurs exactly once, after `## Code Generation Rules` | 0053-llm-python-boundary-claude-md |
| AC-2 | AC | `pytest tests/test_0053_llm_python_boundary.py` passes with the tooled Python. | 0053-llm-python-boundary-claude-md |
| AC-3 | AC | `git diff` on CLAUDE.md shows only the inserted block (additive-only). | 0053-llm-python-boundary-claude-md |
| AC-4 | AC | ≥3 cited helper paths (after stripping `${CLAUDE_PLUGIN_ROOT}/`) exist in the repo. | 0053-llm-python-boundary-claude-md |

## Uncovered

None.

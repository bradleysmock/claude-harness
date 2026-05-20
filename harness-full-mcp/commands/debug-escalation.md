# /debug-escalation

A harness run has been escalated. Diagnose and fix the spec — not the code.

Read the result file. For each failed attempt examine: the gate that failed,
the exact errors, and the LLM's reasoning (`artifact.reasoning`).

## Failure classification

**Class A — Spec ambiguity**
The LLM made a reasonable interpretation of an ambiguous constraint.
The constraint needs to be more specific.

**Class B — Missing context**
The LLM didn't know about a class, pattern, or convention it needed.
Add a `reference_file` or name the thing explicitly in constraints.

**Class C — Contradictory constraints**
Constraints conflict with each other or with acceptance criteria.
One must change.

**Class D — Task too large**
The spec asks for too much in one pass. The LLM can't hold it together.
Split into two specs (or two task specs if this is a task).

**Class E — Harness misconfiguration**
The gate is wrong, not the code — a false positive lint rule, an overly
strict security check. Fix `.harness/config.py`, not the spec.

## Output

State the class and your reasoning, then propose:
- Specific edits to the spec or task file (Class A, B, C, D)
- Specific edits to `.harness/config.py` (Class E)

Do not write the implementation. Do not fix the generated code directly.
Fix the spec; the harness reruns with the corrected spec.

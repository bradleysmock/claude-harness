Debug an escalated run.

If $ARGUMENTS is provided, use it as the run_id. Otherwise call `harness_status(project_root)` to find the most recent escalated run.

Read `.harness/config.py` if it exists to get PROJECT_ROOT (default: .).

## Steps

1. Call `artifact_load(run_id, project_root)`.

2. Read the artifact — implementation, tests, gate_results, attempts.

3. Classify the failure:

   **Class A — Spec ambiguity**: The spec description or acceptance criteria don't specify enough for unambiguous implementation. The implementation was reasonable but wrong.
   → Propose specific edits to the spec's `description` or `acceptance_criteria`.

   **Class B — Missing context**: The implementation imports something that doesn't exist, or assumes an API shape that differs from the actual code.
   → Propose adding the correct file to `reference_files` in the spec.

   **Class C — Environment gap**: A system tool is missing (mypy not installed, go not on PATH, etc.).
   → Tell the user what to install and how to verify it.

   **Class D — Test design flaw**: Tests are testing an internal implementation detail that changed during repair, causing a cascade.
   → Propose revised tests that test behaviour, not implementation.

   **Class E — Genuine hard problem**: The task requires algorithms, data structures, or domain knowledge that made automated repair fail.
   → Summarize what was tried, what failed, and what the remaining gap is. Suggest the user implement manually with the generated code as a starting point.

4. Based on the class:
   - A or B: offer to edit the spec and re-run `/harness:submit`
   - C: provide install instructions, then suggest re-running `/harness:submit`
   - D: offer to revise the tests and re-run
   - E: provide the partial implementation and explain what's left

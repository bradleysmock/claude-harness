Diagnose an escalated harness run.

If $ARGUMENTS is provided, use it as the run ID. Otherwise call `harness_status()` and use the most recent escalated run.

1. Call `harness_debug("<run-id>")`.

2. Classify the failure:
   - **Class A — Spec ambiguity**: LLM made a reasonable but wrong interpretation. Constraint needs to be more specific.
   - **Class B — Missing context**: LLM didn't know about a class, pattern, or convention. Add it to `reference_files` or name it explicitly in constraints.
   - **Class C — Contradictory constraints**: Constraints conflict with each other or with acceptance criteria. One must change.
   - **Class D — Task too large**: Spec asks for too much in one pass. Split into two specs.
   - **Class E — Harness misconfiguration**: Gate is wrong, not the code. Fix `.harness/config.py`.

3. Propose the exact edits to the spec or config file.

4. Tell the user: edit the spec per the proposal, then run `/harness:submit <spec-id>`.

Do not fix or modify the generated code directly. Fix the spec and let the harness regenerate.

Finish a passed run by writing code to its target file.

If $ARGUMENTS is provided, use it as the run_id. Otherwise call `harness_status(project_root)` to find the most recent passed run.

Read `.harness/config.py` if it exists to get PROJECT_ROOT (default: .).

## Steps

1. Call `artifact_load(run_id, project_root)`.

2. Read the artifact:
   - `spec_id` — which spec this is for
   - `implementation` — the passing implementation
   - `tests` — the passing tests
   - `outcome` — must be "passed" (warn and stop if "escalated")

3. Call `spec_load(spec_id, project_root)` to get `target_file`.

4. Write the implementation to `target_file`. If the file already exists, read it first and integrate intelligently (don't blindly overwrite if the file has other classes or functions that should be preserved).

5. Optionally write the tests to an appropriate test file alongside the target (e.g., `tests/test_<module>.py` for Python).

6. Tell the user what was written and suggest:
   - Review the diff before committing
   - Run the tests directly to confirm: `pytest <test_file>`
   - Commit with a message referencing the spec: `git commit -m "feat: <spec description>"`

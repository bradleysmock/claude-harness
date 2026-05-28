# Flow: deliver — spec mode (standalone)

Write a passing spec/build artifact to its target file. No branch involved.

If `$ARGUMENTS` is a run-id, use it. Otherwise call `harness_status(project_root)` to find the most recent passed run.

Read `.harness/config.py` if it exists to get `PROJECT_ROOT` (default `.`).

## Steps

1. Call `artifact(action="load", run_id=run_id, project_root=project_root)`.
2. Confirm `outcome` is `"passed"`. Warn and stop if `"escalated"` — direct the user to invoke the **debug** skill first.
3. Call `spec_load(spec_id, project_root)` to get `target_file`.
4. Write implementation to `target_file`. Integrate intelligently if the file already has other content.
5. Write tests to an appropriate test file alongside the target.
6. Suggest: review the diff, run the tests directly, then commit.

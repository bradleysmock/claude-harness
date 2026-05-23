Run task `$ARGUMENTS` through the harness.

1. Call `harness_task("$ARGUMENTS")` and show per-spec outcomes as layers complete.

2. Based on outcome:
   - **all passed** → tell the user to run `/harness:finish`
   - **any escalated** → list the failed spec IDs and their run IDs, tell the user to run `/harness:debug <run-id>` for each

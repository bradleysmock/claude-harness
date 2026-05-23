Submit spec `$ARGUMENTS` through the harness.

1. Call `harness_score("$ARGUMENTS")` and show the result.
   - If verdict is **block**: stop. Tell the user which dimensions failed and what to fix in the spec before resubmitting.
   - If verdict is **warn**: note the issues and proceed.

2. Call `harness_submit("$ARGUMENTS")` and show the gate results.

3. Based on outcome:
   - **passed** → tell the user to run `/harness:finish`
   - **escalated** → tell the user to run `/harness:debug`

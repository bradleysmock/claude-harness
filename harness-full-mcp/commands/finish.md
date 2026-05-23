A harness run has passed. Deliver the code.

Call `harness_status()` to find the most recent passed run, then read its result file at `.harness/results/<run-id>.json` (or `.task.json` for tasks).

## Steps

1. **Move implementations.** For each passed spec, copy its implementation to `target_file`. Create missing directories. Do not overwrite existing logic — only add or modify what the spec required.

2. **Check for collisions.** If `target_file` already exists, diff carefully before writing.

3. **Update imports.** If the implementation introduces new public symbols that existing files should use, add imports only where the connection is obvious.

4. **Scan related tests.** Read the test directory adjacent to each `target_file`. Flag any existing tests that conflict — do not silently modify them.

5. **Write the commit.**
   ```
   {type}({scope}): {description}

   {one paragraph: what was built and why}

   Assumptions:
   {bullet list from artifact.assumptions}

   Notes:
   {bullet list from artifact.notes, if any}
   ```

6. **Open a draft PR** (if `gh` is available): title = commit first line, body = full commit message, label = `harness-generated`.

Do not push. Do not merge.

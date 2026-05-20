# /finish-task

A harness run has passed. Complete the delivery workflow.

Read the result file (`.harness/results/{id}.json` or `.harness/results/{id}.task.json`).

## Steps

1. **Move implementations.**
   For each passed spec, copy its implementation to its `target_file`.
   Create missing directories. Do not overwrite existing logic — only add
   or modify what the spec required.

2. **Check for collisions.**
   If target_file already exists, diff carefully before writing.

3. **Update imports.**
   If the implementation introduces new public symbols that existing files
   should use, add imports only where the connection is obvious.

4. **Scan related tests.**
   Read the test directory adjacent to each target_file. Flag any existing
   tests that conflict — do not silently modify them.

5. **Write the commit.**
   Stage only the implementation files and any necessary import updates.

   Commit message format:
   ```
   {type}({scope}): {description}

   {one paragraph: what was built and why}

   Assumptions:
   {bullet list from artifact.assumptions, for each spec}

   Notes:
   {bullet list from artifact.notes, if any}
   ```

6. **Open a draft PR** (if `gh` CLI is available):
   - Title: commit message first line
   - Body: full commit message body
   - Label: `harness-generated`

Do not push. Do not merge. Leave that to the developer.

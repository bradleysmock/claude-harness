Initialize the harness in the current project.

1. Create the directory structure:
   ```
   .harness/
   ├── specs/       ← spec files go here
   ├── tasks/       ← task DAG files go here
   ├── results/     ← run artifacts go here
   └── checkpoints/ ← task resume state
   ```

2. Write a config comment to `.harness/config.py`:
   ```python
   # Harness configuration
   # language: python | typescript | go | rust
   LANGUAGE = "python"

   # Root of the project (used for PYTHONPATH injection and file resolution)
   PROJECT_ROOT = "."

   # Maximum repair attempts before escalating
   MAX_REPAIR_ATTEMPTS = 3
   ```

3. Tell the user:
   - The harness is initialized. Edit `.harness/config.py` to set the language.
   - Run `/harness:forge <description>` to write a spec.
   - Run `/harness:submit <spec-id>` to generate and validate code.

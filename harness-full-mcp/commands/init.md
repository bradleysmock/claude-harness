Call `harness_init()`.

Then tell the user:
1. Edit `.harness/config.py` — set `ANTHROPIC_API_KEY` and `project_root`
2. Run `/harness:forge <description>` to write a spec
3. Run `/harness:submit <spec-id>` to generate and gate code
4. Run `/harness:finish` if it passes, `/harness:debug` if it escalates

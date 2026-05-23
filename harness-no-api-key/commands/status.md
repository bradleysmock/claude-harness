Show recent harness runs.

Read `.harness/config.py` if it exists to get PROJECT_ROOT (default: .).

Call `harness_status(project_root)` and display the results.

Format:
- ✓ passed runs — spec-id, timestamp
- ⚠ escalated runs — spec-id, failing gate, timestamp

If there are escalated runs, remind the user: run `/harness:debug` to investigate.
If there are passed runs awaiting write-out, remind the user: run `/harness:finish <run-id>`.

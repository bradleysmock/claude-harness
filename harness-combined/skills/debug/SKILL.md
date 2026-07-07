---
name: debug
description: Classify and explain an escalated spec/build run that exhausted repair attempts, then propose a targeted fix. TRIGGER when the user asks why a build failed, what to do about an escalated run, why repair gave up, how to recover from /build failure, or how to interpret an artifact in .harness/results/ marked escalated (e.g. "why did 0023 escalate?", "the build gave up — what now?", "debug the last run"). SKIP when the build is still in progress, for ordinary test failures inside a ticket worktree (fix directly or run /gate), and for design-phase questions about specs (use /refine instead).
---

# Debug skill — postmortem for escalated runs

Classify and explain an escalated spec/build run.

If `$ARGUMENTS` is provided, use it as the `run_id`. Otherwise call `harness_status(project_root)` (MCP tool) to find the most recent escalated run.

Read `.harness/config.py` if it exists to get `PROJECT_ROOT` (default `.`).

## Steps

1. Call `artifact(action="load", run_id=run_id, project_root=project_root)`.

2. Read the artifact — implementation, tests, `gate_results`, `attempts`.

2.5. **Read the persisted critic findings when present.** If this run corresponds to a
   ticket and `.tickets/XXXX-<slug>/critic-findings.md` exists, read it (see "Critic
   findings file" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). It holds the
   per-round post-build critic reports and, on escalation, the diagnostic subagent's
   root cause / fix strategy / target locations. **Cite those prior rounds and the
   escalation diagnosis instead of re-deriving them** — build your classification on what
   the escalation flow already established (what was tried, why it failed) rather than
   starting from scratch.

3. Classify the failure:

   **Class A — Spec ambiguity**: The spec description or acceptance criteria don't specify enough for unambiguous implementation. The implementation was reasonable but wrong.
   → Propose specific edits to the spec's `description` or `acceptance_criteria`.

   **Class B — Missing context**: The implementation imports something that doesn't exist, or assumes an API shape different from the actual code.
   → Propose adding the correct file to `reference_files` in the spec.

   **Class C — Environment gap**: A system tool is missing (mypy not installed, go not on PATH, etc.).
   → Tell the user what to install and how to verify it.

   **Class D — Test design flaw**: Tests are testing an internal implementation detail that changed during repair, causing a cascade.
   → Propose revised tests that test behavior, not implementation.

   **Class E — Genuine hard problem**: The task requires algorithms, data structures, or domain knowledge that made automated repair fail.
   → Summarize what was tried, what failed, and the remaining gap. Suggest the user implement manually with the generated code as a starting point.

4. Based on the class:
   - **A or B** — offer to edit the spec and re-run `/build <spec-id>`.
   - **C** — provide install instructions, then suggest re-running `/build <spec-id>`.
   - **D** — offer to revise the tests and re-run.
   - **E** — provide the partial implementation and explain what's left.

## Output

Lead with the class (A–E) and the one-line root cause. Then show the proposed fix. Then ask the user whether to apply it. Do not edit files until they confirm.

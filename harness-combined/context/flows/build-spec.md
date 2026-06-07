# Flow: build — spec mode (standalone)

Generate and validate code in a temp dir; store the result as an artifact. No worktree, no commit. Run `/deliver <run-id>` to write to the project when done.

Read `.harness/config.py` if it exists to get `LANGUAGE`, `PROJECT_ROOT`, and `MAX_REPAIR_ATTEMPTS` (defaults: python, `.`, 3).

## Step 0 — Detect spec, task, or free-form description

Decide by what `$ARGUMENTS` is and whether a file matches:

- **Existing spec file** — `.harness/specs/$ARGUMENTS.py` exists → **spec path** (below).
- **Existing task file** — `.harness/tasks/$ARGUMENTS.py` exists → **task path** (below).
- **Bare id, no match** — `$ARGUMENTS` is a single token (no whitespace) and no file matches → **stop**. Tell the user no spec/task named `$ARGUMENTS` exists, and they can pass a description or check the id. Do **not** treat a bare token as a description — this guards against a typo'd id silently triggering a full codebase exploration.
- **Free-form description** — `$ARGUMENTS` contains whitespace (e.g. `add bulk-export endpoint`) → generate the spec inline first: perform the full `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-spec.md` procedure (explore the codebase, write the spec or task DAG to `.harness/specs/` / `.harness/tasks/`). Announce the generated id(s), then continue on the spec or task path below using that id.

## Spec path

**Load:**
- `spec_load("$ARGUMENTS", project_root)`
- `context_fetch(reference_files, target_file, project_root)`

**Generate** implementation and tests in fenced code blocks.

**Gate + repair loop:**
- `gate_run(implementation, tests, language, project_root)`

If fail: save via `artifact(action="save", ...)` → run_id. Then repeat up to `MAX_REPAIR_ATTEMPTS`:
1. `memory(action="retrieve", errors_text=errors_text, gate=gate, project_root=project_root)`
2. Generate unified diff → `repair_run(run_id, diff, language, project_root)`
3. If `{"fallback": "rewrite"}`: full rewrite → `gate_run`

On pass: `memory(action="record", ..., outcome="passed")`, `artifact(action="save", ..., outcome="passed")`. Tell the user: run `/deliver <run-id>`.

On exhaustion: `artifact(action="escalate", run_id=run_id, project_root=project_root)`, `memory(action="record", ..., outcome="escalated")`. Tell the user: invoke the **debug** skill to investigate.

## Task path

Call `dag_load` and `checkpoint(action="read", ...)`. For each spec in each layer, run the spec path above in an isolated subagent. Call `checkpoint(action="write", ...)` after each pass. Report a layer-by-layer table on completion.

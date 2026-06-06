# Design: Fold `/write-spec` into `/build`

**Date:** 2026-06-06
**Status:** Approved (Checkpoint 1)
**Author:** Bradley + Claude

## Problem

The pipeline `/problem → /write-spec → /build → /deliver` has too many discrete
commands, and the `/write-spec` step in particular feels redundant: the lead does
not review the generated spec files before building, so the separate generation
step adds friction without adding value for the common path.

## Goal

Make `/build` the single command for the spec-generation-through-implementation
half of the pipeline, **without losing any feature or quality gate** that
`/write-spec` currently provides.

## Non-goals

- Folding `/deliver` into `/build`. `/deliver` is the lead's post-build diff
  approval — a human gate that stays separate.
- Removing `/write-spec`. It is kept as an optional standalone command for the
  "regenerate or hand-tune the spec only" case.
- Any change to the spec/gate/repair engine, the critic, or the design phase
  (`/problem`).

## What `/write-spec` does today (and why parts are load-bearing)

Ticket mode (`write-spec-ticket.md`):

1. **Scores the design** via `score-spec.md` — a hard BLOCK if `requirements.md`
   / `solution.md` are vague, contain placeholders, or the FR↔test-plan table is
   inconsistent. **This is the real quality gate** and must survive the merge.
2. **Writes spec `.py` / task files** to `.harness/specs/` and `.harness/tasks/`.
   These are not scratch: `dag_load`, `checkpoint`, and the `changes-requested`
   resume path all read them. They must continue to be written to disk.
3. Picks single-spec vs. task DAG.
4. Reads only the files named in `solution.md` (no re-exploration).

Spec mode (`write-spec-spec.md`): full codebase exploration, then writes spec(s).

`/build` today *requires* these files to pre-exist and stops with "run
`/write-spec` first" if they are missing.

## Approach (chosen: Approach A — auto-spec fallback)

`/build` changes from a consumer that *requires* specs to one that *ensures*
specs exist — generating them inline using the exact write-spec procedure, then
building unchanged. Spec/task files still land on disk; they are now authored by
`/build` instead of in a separate step.

Alternatives considered and rejected:

- **Approach B — full merge, delete `/write-spec`.** Loses the standalone
  regenerate/hand-tune path for no meaningful gain over A.
- **Approach C — new `/forge` wrapper.** *Adds* a command rather than removing
  one; contradicts the "too many commands" pain.

### Ticket path (`/build XXXX`)

Replace `build-ticket.md` Step 1's "if neither exists, tell the user to run
`/write-spec` and stop" with an inline branch:

1. Resolve ticket, read `status.md`.
2. Look for `.harness/tasks/XXXX-*` / `.harness/specs/XXXX-*`.
3. **If specs exist** → proceed exactly as today (so `changes-requested` resume
   and re-builds are untouched).
4. **If specs are missing** → run the write-spec **ticket procedure** inline:
   - Require `status: solution`. If earlier and no specs exist → stop, "run
     `/problem XXXX` first" (the existing guardrail, relocated here).
   - Run the **score-spec gate**. **BLOCK → stop before any worktree is
     created** — print failing checks; the lead fixes design artifacts.
   - Read only the files named in `solution.md`, pick single-spec vs. DAG, write
     the spec/task files to disk.
   - Announce: "No specs found — generated N spec(s) from `solution.md`
     (score-spec: PASS/WARN)." The lead always sees that auto-spec happened.
5. Continue to worktree creation → DAG load → execute → commit → diff → critic,
   unchanged.

### Standalone path (`/build <arg>`)

Disambiguate on argument shape (mirrors how `/write-spec` already picks its
mode):

- **Bare id, no spaces** (e.g. `auth-login`) with no matching file → error as
  today ("no spec found"). Protects against a typo'd id silently triggering a
  full exploration + build.
- **Free-form description, has spaces** (e.g. `add bulk-export endpoint`) → run
  the write-spec **spec procedure** inline (full codebase exploration), write
  spec files, then build. Opt-in by virtue of typing a description; the
  exploration cost lands in `/build`.

## What is explicitly preserved

- **score-spec BLOCK gate** — moved earlier in `/build`, never dropped.
- **Spec/task files on disk** — still written; DAG, checkpoint, and resume all
  keep working.
- **`/write-spec` command** — kept as-is.
- **`/deliver`** — untouched; post-build diff approval stays a separate human
  gate.

## Files to change (all prompt/markdown — no engine code)

Edit the **project-root** copies (per CLAUDE.md, not the plugin-dir copies):

1. `commands/build.md` — update both mode descriptions (drop "run /write-spec
   first and stop").
2. `context/flows/build-ticket.md` — Step 1 rewrite above; relocate the
   status/score-spec gate to fire before worktree creation.
3. `context/flows/build-spec.md` — Step 0 disambiguation + inline spec-mode
   generation.
4. `CLAUDE.md` — pipeline diagram marks `/write-spec` optional; update the
   `/clear` session-boundary note to reference just `/build`.
5. `context/harness-reference.md` — status table note: `solution → implementing`
   can now be driven by `/build` directly.
6. `README.md` catalog — reflect that `/build` self-specs.

## Verification

These are instruction files, not code, so no unit tests. Verification is a
dry-run on two tickets:

1. A ticket with specs already present → must behave identically to today.
2. A ticket at `status: solution` with no specs → must auto-spec, honor a
   score-spec BLOCK (stop before worktree), and otherwise build through to the
   diff and critic.

Also confirm the standalone disambiguation: a bare unknown id errors; a
multi-word description triggers explore → spec → build.

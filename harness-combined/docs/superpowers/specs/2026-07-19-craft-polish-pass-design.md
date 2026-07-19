# Design: Craft polish pass (gate-locked, behaviour-preserving)

**Date:** 2026-07-19
**Status:** Proposed (Checkpoint 1 pending)
**Author:** Bradley + Claude
**Origin:** Ports "Refinement 8: Craft Polish Pass" (authored for the older
`harness-full` in-process architecture) onto the active `harness-combined`
Claude-Code-orchestrated pipeline. Rationale: `BEAUTIFUL_CODE.md` §5.4 — functional
verification is solved and iterated; craft is not iterated at all.

## Problem

The pipeline has iteration for functional defects (the gate repair loop, the
critic BLOCKER/MAJOR auto-repair loop) and **no iteration for craft**. The critic
*does* observe craft — `critic-brief.md` scores naming precision (Dimension 3) —
but craft findings land as **MINOR/OBS, which are advisory-only and never applied**
(`build-ticket.md` Step 7c). So "this name is wrong / this function should be
split / this comment is noise" dies as a logged note the lead may ignore.

The closest mechanical analogue to a human engineer writing, reading, feeling the
wrongness, and revising is a post-acceptance pass that *proposes* craft
improvements, *applies* them, and *re-proves behaviour* by re-running the gates —
discarding any change that breaks them. `harness-combined` already has every
primitive this needs; they are just not assembled into that loop.

## Goal

Add a craft polish stage that runs **after functional acceptance**, iteratively
improves the worktree's craft (naming, structure, restraint, load-bearing
comments) **without changing behaviour**, and enforces behaviour preservation
mechanically by re-running the existing gates plus a pinned-test-survival check
against every polished candidate.

Pipeline position (mirrors the original spec's `gates → verifier → alignment →
CRAFT → accept`, mapped to this pipeline):

```
gate repair loop → critic BLOCKER/MAJOR auto-repair (7a/7b) → CRAFT POLISH (new 7b.5) → deliver
```

Polishing runs only once functional review has approved the worktree: polishing
broken code is wasted, and polishing before the critic's must-fix loop converges
risks the polish fighting an in-flight repair.

## Non-goals

- Any behaviour change. The pass is craft-only; the gates are the enforcement.
- A second correctness reviewer. That is the critic's job; craft polish does not
  re-open BLOCKER/MAJOR findings.
- Touching MINOR/OBS *triage*. The lead still decides on residual advisory
  findings; polish acts on its own proposals, not on the critic's logged notes.
- Spec-mode (`build-spec.md`) in v1. It has no critic loop and a single temp-dir
  artifact; a follow-up can extend polish there once proven in ticket mode.

## Translation: `harness-full` spec → `harness-combined` reality

| Original (`harness-full`) | `harness-combined` equivalent |
|---|---|
| `CraftPolishPass` class, in-process | A `craft` **subagent** (`agents/craft.md`), modeled on `critic` |
| `llm_client` | The subagent's own model invocation (Claude Code drives it) |
| `gate_runner(candidate)` callable | `gate_run_on_dir(worktree, "auto", project_root)` + ticket 0041 baseline-delta |
| `GeneratedArtifact` (impl/tests/reasoning/confidence) | The committed worktree files (impl + tests); `.harness/results/*.json` for spec-mode |
| Asymmetric exposure (hide `confident_about`/`uncertain_about`/`falsification`) | The critic pattern already hides implementer reasoning from the reviewer — inherited free |
| `event_bus` `craft.*` events | Structured status lines in the flow + `.harness/craft/<ticket>.json` report |
| `require_test_survival` | Pinned pre-polish tests re-run against the polished implementation (below) |
| `CraftPolishConfig`, `max_iterations` | `CRAFT_MAX_ITERATIONS` in `.harness/config.py` (default 3; `0` disables) |

The load-bearing observation: **behaviour preservation is already built.**
`gate_run_on_dir` + 0041's baseline-delta is exactly "re-run gates against every
candidate, discard on any new failure or regression." The port reuses it rather
than reinventing the original spec's `gate_runner`.

## Architecture

### 1. The `craft` subagent (`agents/craft.md`)

Read-only-reasoning reviewer that emits **structured improvements**, not prose.
Modeled on `critic` (asymmetric exposure, "your response is the entire
deliverable"). Its prompt:

- Includes the spec/ticket intent (`solution.md` description + constraints) and the
  current worktree implementation and tests.
- Does **not** include any implementer reasoning/confidence framing (the critic
  already withholds this; the subagent boundary enforces it).
- Contains the exact phrase **"behaviour must not change"** and the bounded
  seven-value taxonomy: `rename | extract | inline | comment | delete | simplify |
  error_handling`. Every proposed improvement falls into exactly one; each
  rationale must cite a specific identifier or line pattern (generic rationales
  disallowed).
- Emits JSON in fixed order: `reasoning`, `improvements[]`
  (`{category, location_hint, rationale}`), `polished_implementation`,
  `polished_tests`.

The taxonomy maps onto existing lenses: `simplify`/`extract`/`inline` are the
`/code-review` and (session-level) simplify concerns; `rename` is critic
Dimension 3; `comment`/`delete` are the "load-bearing comments / restraint"
concerns from `BEAUTIFUL_CODE.md`.

### 2. New flow step — `build-ticket.md` Step 7b.5 (gate-locked polish loop)

Runs after Step 7b (critic must-fix findings cleared) and before the delivery
handoff. Skipped entirely when `CRAFT_MAX_ITERATIONS == 0` (report
`final_status="disabled"`).

Before the loop: **pin the baseline** — record the worktree's current HEAD SHA and
capture the pre-polish test files (they are already committed at Step 5 / 7a). This
pinned test set is the anti-cheat reference.

For each iteration `N` (1 … `CRAFT_MAX_ITERATIONS`):

1. Spawn the `craft` subagent. If it returns an **empty** `improvements` list →
   `final_status="converged"`, stop (this counts as an iteration run).
2. Apply `polished_implementation` / `polished_tests` to the worktree.
3. **Behaviour-preservation gate (discard-on-break):**
   a. `gate_run_on_dir(worktree, "auto", project_root)` — any new failure or 0041
      baseline regression → **revert this round** (`git -C worktree checkout .` to
      the pre-round state), record every improvement in the round as
      `was_applied=False` with `rejection_reason` naming the failing gate, continue
      to `N+1` from the prior good state.
   b. **Pinned-test-survival:** run the *pre-polish* test files against the
      *polished implementation* in a scratch overlay. If any pre-polish test now
      fails, the polish changed behaviour (or weakened a test to pass the gate) →
      revert the round, `rejection_reason="pinned test <id> failed"`. This is the
      `require_test_survival` translation and the primary drift guard.
4. If both pass → commit the round
   (`git -C worktree commit -am "polish: craft round N"`), record improvements as
   `was_applied=True`.
5. Reaching `CRAFT_MAX_ITERATIONS` without convergence →
   `final_status="max_iterations_reached"`.

Because each accepted round is a separate commit, the lead sees craft changes as a
distinct, revertable slice in the Step 6 diff — never entangled with the functional
implementation.

### 3. Report + instrumentation

Write `.harness/craft/<ticket>.json` (a `CraftPolishReport`: `iterations_run`,
`improvements_applied[]`, `improvements_rejected[]`, `final_status`) and display a
`formatted()` summary. The original spec's `craft.*` events become deterministic
status lines: `started` / `iteration` (once per iteration incl. the terminal
convergence one) / `improvement_applied` / `improvement_rejected` / `completed`
(started + completed exactly once per invocation).

### 4. Config (`.harness/config.py`)

`CRAFT_MAX_ITERATIONS: int = 3` (`0` disables — the pass returns the worktree
unchanged, `final_status="disabled"`). Optional `CRAFT_REQUIRE_TEST_SURVIVAL: bool
= True`.

## Why the drift risk is well-controlled here

The original spec's named risk — "polish reintroduces behaviour drift the gates
miss." In `harness-combined` this is unusually well-defended:

- The gate suite is strong: type + lint + test + security, run full-suite per 0041.
- 0041 pins the merge-base test failure set, so *new* failures are caught even
  amid unrelated pre-existing red.
- The pinned-test-survival check (2.3b) blocks the specific failure mode of the
  polisher weakening a test to make the gate green — which the critic already
  treats as a BLOCKER (`critic-brief.md:55`), so the value is doubly encoded.

## Composition with in-flight designs

- **Failure memory (0052 `resolution` + the forward-injection proposal):** a
  rejected polish round is a `passed`-adjacent learning — record it as
  `memory(action="record", gate="craft", errors_text=<gate that broke>,
  outcome="escalated", resolution=<what the polish tried>)`. Future craft rounds in
  the same area can then avoid the same dead-end proposal.
- **Critic:** craft polish consumes the critic's *approval* as its precondition and
  never re-litigates correctness; the two loops stay orthogonal.

## Files to change

New:

1. `agents/craft.md` — the craft subagent (taxonomy, asymmetric exposure,
   JSON contract, "behaviour must not change").
2. `docs/superpowers/specs/…` (this doc).

Prompt/flow (project-root copies, per `CLAUDE.md`):

3. `context/flows/build-ticket.md` — new Step 7b.5; thread `CRAFT_MAX_ITERATIONS`;
   note the polish commits in Step 6's diff summary.
4. `context/harness-reference.md` — document the craft stage, its gate-lock, and
   the `.harness/craft/` report in the pipeline/repair-loop sections.
5. `README.md` — add craft polish to the pipeline description.
6. `.gitignore` — ignore `.harness/craft/` (ephemeral, like `results/`).

No MCP server code strictly required — behaviour preservation reuses the existing
`gate_run_on_dir` tool. (Optional later: a thin `craft_report` tool if the JSON
report should be server-managed rather than written by the flow.)

## Verification

Flow-level dry runs (this is prompt/agent wiring, like the `/write-spec` fold):

1. **Disabled:** `CRAFT_MAX_ITERATIONS=0` → worktree unchanged,
   `final_status="disabled"`, `iterations_run=0`.
2. **Immediate convergence:** craft subagent returns empty `improvements` →
   unchanged worktree, `iterations_run=1`, `final_status="converged"`.
3. **Rejected improvement:** a proposed rename that breaks a gate →
   `was_applied=False`, `rejection_reason` names the failing gate, worktree reverts
   to the pre-round commit.
4. **Test-weakening blocked:** a polish that loosens an assertion to pass the gate →
   caught by pinned-test-survival, reverted.
5. **Max iterations:** continuous warranted improvements →
   `final_status="max_iterations_reached"`, each accepted round a separate commit.
6. **Prompt contract:** the craft prompt never contains `confident_about` /
   `uncertain_about` / `falsification`, and contains "behaviour must not change".

Empirical success signal (from the origin spec, adapted): on a held-out set of
tickets, ≥50% reduction in craft-category critic findings (naming, function-length,
"why is this comment here") between polish-disabled and polish-enabled runs, with
**no** increase in functional/BLOCKER findings (which would indicate the polish is
sneaking behaviour changes past the gates).

## Open decisions for Checkpoint 1

1. **Placement:** Step 7b.5 (post-critic, pre-deliver) as above, or a separate
   opt-in `/polish XXXX` command so craft runs on demand rather than every build?
2. **Re-review after polish:** re-spawn the critic once post-polish to confirm the
   craft changes introduced no new MINOR/OBS churn, or trust the gate-lock and
   skip the extra critic pass (cost vs. assurance)?
3. **Scope of `delete`:** allow the polisher to delete apparently-dead code, or
   restrict deletion to comments only in v1 (dead-code deletion is the highest-risk
   category for silent behaviour change)?

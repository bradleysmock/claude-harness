# Flow: autopilot — ticket mode

Autonomous build-to-deliver pipeline. The ticket is confirmed at `status: solution`.

**Announce**: "Autopilot mode for XXXX-slug."

<!-- progress-checklist -->
**Progress checklist** — as the first action of this run, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). This is the parent run; the `build-ticket.md` and `deliver-ticket.md` sub-flows adopt this same list rather than creating their own:

`Generate specs (if needed) · Build XXXX in worktree · Critic + auto-repair · Merge worktree · Status → done + archive · Cleanup`

## Steps 1–7c — Build

Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-ticket.md` and follow it exactly through Steps 1–7c: worktree creation, spec generation (if specs are absent), spec execution, gate repair loop, worktree commit, diff display, critic spawn, and BLOCKER/MAJOR auto-repair.

**Spec-BLOCK interception**: When the score-spec gate in `build-ticket.md` Step 1 returns **BLOCK** (the condition that would normally hard-stop *before any worktree is created* and hand back to the lead), stop following `build-ticket.md` and continue in this flow at **Step S** below. Step S is the *only* override of that hard stop — any context that reaches the BLOCK without this interception keeps the fail-closed hard stop.

**Divergence condition**: When BLOCKER/MAJOR findings still remain after `MAX_REPAIR_ATTEMPTS` repair rounds (the condition that would normally trigger `build-ticket.md` Step 7d), stop following `build-ticket.md` and continue in this flow at Step A below.

**Clean-build interception**: When the critic returns no BLOCKER/MAJOR findings (the condition that would normally trigger `build-ticket.md` Step 7b or 7c — 7b = repair loop cleared findings; 7c = no must-fix findings from the start), stop following `build-ticket.md` and continue in this flow at Step B below.

## Step S — Spec auto-remediation (autopilot only)

Reached only via the Spec-BLOCK interception above — a score-spec **BLOCK** at
`build-ticket.md` Step 1, *before* any worktree exists. Do **not** hand back to the
lead yet; do **not** create a worktree.

Read `${CLAUDE_PLUGIN_ROOT}/context/spec-remediation.md` and follow it. It
classifies the BLOCK checks, applies the bounded budget (≤1 mechanical pass + ≤1
`/refine` pass, each committed to `main` and re-scored on the committed files), and
returns one of three outcomes:

- **`succeeded(autonomous=True)`** — cleared by mechanical fixes only. Re-enter
  `build-ticket.md` at Step 1 (specs now generate against the PASS/WARN artifacts)
  and continue the build normally. Step B auto-delivers as usual.
- **`succeeded(autonomous=False)`** — a semantic `/refine` pass was needed. Re-enter
  `build-ticket.md` at Step 1 and build normally, but **mark this run "refine-touched"**
  so Step B confirms the diff instead of auto-delivering (unapproved scope must not
  merge unseen).
- **`bail`** — budget exhausted, an unrecognised BLOCK check, or `/refine` could not
  drive the fix from existing text. No worktree was created. Show the residual
  score-spec checks and tell the lead:
  > Autopilot could not auto-remediate the score-spec BLOCK (mechanical + one
  > `/refine` pass did not clear it, or a check fell outside the remediation recipe).
  > Fix the design artifacts (or run `/refine XXXX`) and re-run `/autopilot XXXX`.

  Then stop — this is the same terminal state interactive `/build` reaches on BLOCK.

## Step A — Repair exhaustion

Do **not** transition to `changes-requested`. Do **not** ask the lead.

Read `${CLAUDE_PLUGIN_ROOT}/context/flows/repair-escalation.md` and follow it.

**If repair-escalation returns succeeded** → go to Step B. (Ticket status remains `review-ready` — repair-escalation does not change it.)

**If repair-escalation returns exhausted**:
1. Transition `status.md` to `status: changes-requested` and commit the metadata transition to `main` (scoped add — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):
   ```
   git add .tickets/XXXX-slug/
   git commit -m "chore(ticket): XXXX → changes-requested"
   ```
2. Show the residual BLOCKER/MAJOR findings.
3. Tell the lead:
   > Auto-repair could not clear all BLOCKER/MAJOR findings after full escalation (diagnostic subagent + strategy reset). Options:
   > - Advise on the approach, then run `/build XXXX` to resume repair with the existing worktree.
   > - Run `/review XXXX` for an interactive panel-aware deep-dive on the residual findings.

## Step B — Auto-deliver

Show the diff (informational — not a gate):

```
git -C .worktrees/XXXX-slug diff main
```

**Refine-touched carve-out**: if Step S returned `succeeded(autonomous=False)` for
this run (a semantic `/refine` pass revised `requirements.md`/`solution.md`), the
scope was machine-adjusted and must not merge unseen. Show the diff **and** the
`/refine` audit trail, then stop and ask the lead to confirm before delivering —
do **not** skip the confirmation. Deliver only on explicit approval.

Otherwise (a clean build, or Step S cleared the BLOCK with mechanical fixes only —
`succeeded(autonomous=True)` — or Step S was never entered), read
`${CLAUDE_PLUGIN_ROOT}/context/flows/deliver-ticket.md` and follow it, **skipping
Step 3 (the "Proceed? yes/no" confirmation prompt)** — proceed directly from Step 2
to Step 4. No approval from the lead is required in autopilot mode.

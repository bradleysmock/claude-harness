# Flow: autopilot — ticket mode

Autonomous build-to-deliver pipeline. The ticket is confirmed at `status: solution`.

**Announce**: "Autopilot mode for XXXX-slug."

## Steps 1–7c — Build

Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-ticket.md` and follow it exactly through Steps 1–7c: worktree creation, spec generation (if specs are absent), spec execution, gate repair loop, worktree commit, diff display, critic spawn, and BLOCKER/MAJOR auto-repair.

**Divergence condition**: When BLOCKER/MAJOR findings still remain after `MAX_REPAIR_ATTEMPTS` repair rounds (the condition that would normally trigger `build-ticket.md` Step 7d), stop following `build-ticket.md` and continue in this flow at Step A below.

**Clean-build interception**: When the critic returns no BLOCKER/MAJOR findings (the condition that would normally trigger `build-ticket.md` Step 7b or 7c — 7b = repair loop cleared findings; 7c = no must-fix findings from the start), stop following `build-ticket.md` and continue in this flow at Step B below.

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

Read `${CLAUDE_PLUGIN_ROOT}/context/flows/deliver-ticket.md` and follow it, **skipping Step 3 (the "Proceed? yes/no" confirmation prompt)** — proceed directly from Step 2 to Step 4. No approval from the lead is required in autopilot mode.

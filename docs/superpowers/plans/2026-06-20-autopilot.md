# `/autopilot` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/autopilot XXXX` command that chains build → extended repair → deliver, enabling a two-touch workflow: `/problem` for design, `/autopilot` for execution.

**Architecture:** Three new markdown instruction files in `harness-combined/`. No existing files are modified. `autopilot-ticket.md` delegates to `build-ticket.md` for Steps 1–7c, intercepts at the exhaustion point to call `repair-escalation.md`, and on success calls `deliver-ticket.md` (skipping its confirmation prompt).

**Tech Stack:** Markdown instruction files following the existing harness-combined flow convention. No code changes.

## Global Constraints

- No existing files modified — `build-ticket.md`, `deliver-ticket.md`, and all commands are untouched.
- All flow file references use `${CLAUDE_PLUGIN_ROOT}/` prefix.
- Return signals between flows use bold keywords: **succeeded** and **exhausted**.
- `deliver-ticket.md` Step 3 (confirmation prompt) is explicitly skipped by `autopilot-ticket.md`.

---

### Task 1: `commands/autopilot.md`

**Files:**
- Create: `harness-combined/commands/autopilot.md`

**Interfaces:**
- Consumes: nothing (entry point)
- Produces: delegates to `${CLAUDE_PLUGIN_ROOT}/context/flows/autopilot-ticket.md`

**Verification checklist** (read the file after writing and confirm each):
- [ ] Ticket resolution scans `.tickets/<arg>*/` then `.tickets/completed/<arg>*/`
- [ ] Empty `$ARGUMENTS` case: scans for exactly one `status: solution` ticket; lists and stops if multiple
- [ ] Status precondition: if not `status: solution`, directs to `/problem XXXX`
- [ ] Announces resolved ticket before delegating
- [ ] Delegates via `read … and follow it` pattern (matches existing command convention)

- [ ] **Step 1: Write the file**

Create `harness-combined/commands/autopilot.md` with this exact content:

```markdown
Run `$ARGUMENTS` through the full autonomous pipeline: spec generation (if needed), build-with-extended-repair, and auto-deliver on success.

Requires the ticket to be at `status: solution`. If not, stop and tell the lead to run `/problem XXXX` first.

## Ticket Resolution

If `$ARGUMENTS` begins with four digits, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found. Confirm the matched ticket is at `status: solution`. If the status is not `solution`, stop and tell the lead to run `/problem XXXX` first.

If `$ARGUMENTS` is empty, scan `.tickets/` (not `.tickets/completed/`) for tickets with `status: solution`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before proceeding.

If no ticket is found, stop and report.

State the resolved ticket in one sentence — "Autopilot mode for XXXX-slug" — then read `${CLAUDE_PLUGIN_ROOT}/context/flows/autopilot-ticket.md` in full and follow it.
```

- [ ] **Step 2: Verify against checklist**

Read the file and confirm every item in the verification checklist above is satisfied.

- [ ] **Step 3: Commit**

```bash
git add harness-combined/commands/autopilot.md
git commit -m "feat: add /autopilot command entry point"
```

---

### Task 2: `context/flows/repair-escalation.md`

**Files:**
- Create: `harness-combined/context/flows/repair-escalation.md`

**Interfaces:**
- Consumes: active worktree at `.worktrees/XXXX-slug/`, `gate-findings.md`, latest critic report in context, spec file(s), `MAX_REPAIR_ATTEMPTS` config value
- Produces: returns **succeeded** or **exhausted** signal to caller (`autopilot-ticket.md`)

**Verification checklist:**
- [ ] Phase 1 spawns a read-only `claude` subagent — brief includes spec files, implementation, tests, gate-findings.md, and verbatim BLOCKER/MAJOR findings
- [ ] Subagent brief asks for exactly three outputs: root cause, fix strategy, target locations
- [ ] Phase 1 applies the strategy, re-runs `gate_run_on_dir`, re-spawns critic — up to `MAX_REPAIR_ATTEMPTS` rounds
- [ ] Phase 1 returns **succeeded** on clean critic; falls to Phase 2 on remaining findings
- [ ] Phase 2 deletes (not `git checkout`) the failing target file(s) before rewriting
- [ ] Phase 2 prepends "previous approaches + root cause" to generation context
- [ ] Phase 2 runs gate + critic with up to `MAX_REPAIR_ATTEMPTS` rounds
- [ ] Phase 2 returns **succeeded** on clean critic; returns **exhausted** on remaining findings
- [ ] Both return signals are bolded (`**succeeded**`, `**exhausted**`) for unambiguous detection by the caller

- [ ] **Step 1: Read `build-ticket.md` Steps 7 and 7a–7d to understand the exact state at entry**

```bash
grep -n "Step 7" harness-combined/context/flows/build-ticket.md
```

Confirm: on entry to repair-escalation, the worktree exists, `gate-findings.md` is written, and the latest critic report is in context. Note the exact `gate_run_on_dir` call signature used in Step 7a so repair-escalation matches it.

- [ ] **Step 2: Write the file**

Create `harness-combined/context/flows/repair-escalation.md` with this exact content:

```markdown
# Flow: repair-escalation

Entered when BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` in the post-build critic loop. The worktree exists at `.worktrees/XXXX-slug/`, `gate-findings.md` is current at `.tickets/XXXX-slug/gate-findings.md`, and the latest critic report is in context.

This flow returns one of two signals to the caller:
- **succeeded**: all BLOCKER/MAJOR findings cleared
- **exhausted**: findings remain after all phases

## Phase 1 — Diagnostic subagent

Spawn a `claude` subagent (fresh context, read-only — it must not write or edit files) with the following brief. Substitute the actual ticket slug, spec paths, implementation paths, and critic findings before spawning:

> You are a diagnostic engineer. A build repair loop has exhausted MAX_REPAIR_ATTEMPTS without clearing all BLOCKER/MAJOR findings. Do not write or edit anything — only diagnose.
>
> Read:
> - The failing spec file(s): [list paths from `.harness/specs/` or `.harness/tasks/`]
> - The current implementation: [`.worktrees/XXXX-slug/<target_file>`]
> - The current tests: [`.worktrees/XXXX-slug/tests/`]
> - Gate findings: `.tickets/XXXX-slug/gate-findings.md`
> - BLOCKER/MAJOR findings from the latest critic report: [paste them verbatim]
>
> Produce exactly three things:
> 1. **Root cause** — what is fundamentally wrong (not a restatement of error messages)
> 2. **Fix strategy** — a concrete approach that avoids what was already tried
> 3. **Target locations** — which files and sections to change

Apply the subagent's fix strategy: make the targeted edits directly in `.worktrees/XXXX-slug/`, then run:

```
gate_run_on_dir(".worktrees/XXXX-slug", "auto", project_root)
```

Re-spawn the critic subagent (same Phase and Ticket as the caller, next Round number). Display its report verbatim. Allow up to `MAX_REPAIR_ATTEMPTS` additional repair rounds.

- If the critic returns no BLOCKER/MAJOR findings → **return succeeded** to caller.
- If BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` → proceed to Phase 2.

## Phase 2 — Strategy reset

Delete the failing target file(s) from the worktree (do not use `git checkout` — the goal is a clean slate, not the last committed version):

```
rm .worktrees/XXXX-slug/<target_file>
```

Rewrite the target file(s) from the spec. Prepend the following to the generation context before writing:

> Previous approaches tried: [brief summary of what the original repair loop and Phase 1 attempted]. These failed because: [root cause identified by the Phase 1 diagnostic subagent]. Do not use these approaches.

Run `gate_run_on_dir` and re-spawn the critic. Display the critic's report verbatim. Allow up to `MAX_REPAIR_ATTEMPTS` rounds.

- If the critic returns no BLOCKER/MAJOR findings → **return succeeded** to caller.
- If BLOCKER/MAJOR findings remain → **return exhausted** to caller.
```

- [ ] **Step 3: Verify against checklist**

Read the file and confirm every item in the verification checklist above is satisfied.

- [ ] **Step 4: Commit**

```bash
git add harness-combined/context/flows/repair-escalation.md
git commit -m "feat: add repair-escalation flow (diagnostic subagent + strategy reset)"
```

---

### Task 3: `context/flows/autopilot-ticket.md`

**Files:**
- Create: `harness-combined/context/flows/autopilot-ticket.md`

**Interfaces:**
- Consumes: ticket at `status: solution`; delegates to `build-ticket.md` Steps 1–7c; calls `repair-escalation.md`; calls `deliver-ticket.md` skipping Step 3
- Produces: ticket ends at `status: done` (success) or `status: changes-requested` (exhausted)

**Verification checklist:**
- [ ] Announces "Autopilot mode for XXXX-slug" as preamble
- [ ] Delegates to `build-ticket.md` with explicit "stop at exhaustion condition" instruction
- [ ] Exhaustion condition is stated as: BLOCKER/MAJOR findings remain after `MAX_REPAIR_ATTEMPTS` (not just "Step 7d")
- [ ] On exhaustion: does NOT transition to `changes-requested` before calling repair-escalation
- [ ] On repair-escalation **succeeded**: goes to auto-deliver
- [ ] On repair-escalation **exhausted**: transitions to `changes-requested` (with metadata commit), shows residual findings, presents recovery options
- [ ] On clean build (7b/7c): goes directly to auto-deliver without presenting options
- [ ] Auto-deliver: shows diff first (informational)
- [ ] Auto-deliver: calls `deliver-ticket.md` explicitly skipping Step 3 (confirmation prompt)
- [ ] No interactive approval prompt at any point in the success path

- [ ] **Step 1: Verify deliver-ticket.md Step 3 content**

```bash
grep -n "Proceed\|confirm\|yes/no\|Step 3" harness-combined/context/flows/deliver-ticket.md
```

Confirm Step 3 is the "Proceed? (yes/no)" confirmation prompt. Note the step number so the skip instruction in autopilot-ticket.md is exact.

- [ ] **Step 2: Write the file**

Create `harness-combined/context/flows/autopilot-ticket.md` with this exact content:

```markdown
# Flow: autopilot — ticket mode

Autonomous build-to-deliver pipeline. The ticket is confirmed at `status: solution`.

**Announce**: "Autopilot mode for XXXX-slug."

## Steps 1–7c — Build

Read `${CLAUDE_PLUGIN_ROOT}/context/flows/build-ticket.md` and follow it exactly through Steps 1–7c: worktree creation, spec generation (if specs are absent), spec execution, gate repair loop, worktree commit, diff display, critic spawn, and BLOCKER/MAJOR auto-repair.

**Divergence condition**: When BLOCKER/MAJOR findings still remain after `MAX_REPAIR_ATTEMPTS` repair rounds (the condition that would normally trigger `build-ticket.md` Step 7d), stop following `build-ticket.md` and continue in this flow at Step A below.

**Clean-build interception**: When the critic returns no BLOCKER/MAJOR findings (the condition that would normally trigger `build-ticket.md` Step 7b or 7c), stop following `build-ticket.md` and continue in this flow at Step B below.

## Step A — Repair exhaustion

Do **not** transition to `changes-requested`. Do **not** ask the lead.

Read `${CLAUDE_PLUGIN_ROOT}/context/flows/repair-escalation.md` and follow it.

**If repair-escalation returns succeeded** → go to Step B.

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
```

- [ ] **Step 3: Verify against checklist**

Read the file and confirm every item in the verification checklist above is satisfied.

- [ ] **Step 4: Trace the three key scenarios**

Read through `autopilot-ticket.md` while mentally simulating each:

1. **Happy path**: build succeeds, critic clean on first round → Step B → diff shown → deliver runs → done.
2. **Escalation succeeds**: MAX_REPAIR_ATTEMPTS exhausted → Step A → repair-escalation returns succeeded → Step B → deliver → done.
3. **Full exhaustion**: MAX_REPAIR_ATTEMPTS exhausted → Step A → repair-escalation returns exhausted → changes-requested, recovery options shown.

Confirm the flow handles all three without ambiguity.

- [ ] **Step 5: Commit**

```bash
git add harness-combined/context/flows/autopilot-ticket.md
git commit -m "feat: add autopilot-ticket flow (build-to-deliver with extended repair)"
```

---

### Task 4: Integration check and push

**Files:**
- Read-only verification across all three new files

- [ ] **Step 1: Verify all three files exist**

```bash
ls harness-combined/commands/autopilot.md \
   harness-combined/context/flows/autopilot-ticket.md \
   harness-combined/context/flows/repair-escalation.md
```

Expected: all three paths listed with no errors.

- [ ] **Step 2: Verify cross-references are consistent**

```bash
grep "repair-escalation" harness-combined/context/flows/autopilot-ticket.md
grep "autopilot-ticket" harness-combined/commands/autopilot.md
grep "deliver-ticket" harness-combined/context/flows/autopilot-ticket.md
grep "build-ticket" harness-combined/context/flows/autopilot-ticket.md
```

Expected: each grep returns exactly one match with the correct `${CLAUDE_PLUGIN_ROOT}/context/flows/` prefix.

- [ ] **Step 3: Verify return signals match**

```bash
grep "succeeded\|exhausted" harness-combined/context/flows/repair-escalation.md
grep "succeeded\|exhausted" harness-combined/context/flows/autopilot-ticket.md
```

Expected: repair-escalation.md emits `**return succeeded**` and `**return exhausted**`; autopilot-ticket.md reads `**returns succeeded**` and `**returns exhausted**` (caller-side wording). Confirm the bolded keywords match.

- [ ] **Step 4: Verify deliver-ticket Step 3 skip is explicit**

```bash
grep "Step 3\|skip" harness-combined/context/flows/autopilot-ticket.md
```

Expected: a line explicitly naming "Step 3" and "skipping" or "skip".

- [ ] **Step 5: Push**

```bash
git push
```

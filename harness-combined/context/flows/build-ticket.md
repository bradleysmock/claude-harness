# Flow: build — ticket mode

Create a worktree, run the spec engine against it, write passing implementations to target files in the worktree, and present a diff for review.

Read `.harness/config.py` if it exists to get `LANGUAGE`, `PROJECT_ROOT`, and `MAX_REPAIR_ATTEMPTS` (defaults: auto-detect, `.`, 3).

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

`Generate specs (if needed) · Build XXXX in worktree · Critic + auto-repair · Present diff (Checkpoint 2)`

**Sub-flow note:** this flow may run as a sub-flow under `/autopilot`. If a checklist already exists for this run (autopilot created it), follow the convention's one-list-per-run rule — adopt that existing list and advance its stages, do **not** create a second one.

## Step 1 — Resolve ticket, ensure specs exist

Scan `.tickets/` for the ticket matching `$ARGUMENTS`; if not found, scan `.tickets/completed/`. Read `status.md` to get the slug. Use whichever location the ticket is found in for all subsequent file references in this flow.

Resolve the ticket's status via the **Ticket resolution** rule in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`: the claim-time worktree `.worktrees/XXXX-<slug>` already exists, so its `.tickets/` copy of `status.md` (and its `solution.md` / `requirements.md`) is authoritative; the root copy shows only claim/terminal states. Read the design artifacts scored below from the worktree copy.

If `status` is `changes-requested`, the worktree already exists from a prior `/build`. Skip Step 2; resume with the existing worktree and skip already-passed specs via `checkpoint(action="read", ...)`.

Find the spec or task for this ticket:
- `.harness/tasks/XXXX-<slug>.py` — multi-spec task (preferred if it exists)
- `.harness/specs/XXXX-<slug>*.py` — individual spec(s)

**If specs exist** — continue to the standards/learnings load below.

**If neither exists** — generate them inline before building (this replaces the old "run `/write-spec` first" hand-off):

1. Perform **Steps 1–5** of `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-ticket.md` (resolve + score-spec gate → read only the named files → choose single-spec vs DAG → write the spec/task files). **Skip that flow's Step 6 report** — you are continuing into the build, not handing off.
2. **score-spec is a hard stop.** That flow's Step 1 runs the score-spec gate; if its verdict is **BLOCK**, stop here — **before any implementation is written** (the claim-time worktree already exists; leave it holding only its design artifacts) — show the failing checks, and tell the lead to fix the design artifacts (or run `/refine XXXX`) and re-run `/build XXXX`. This hard stop is the **fail-closed default**; it is overridden *only* when this flow runs as a sub-flow under `/autopilot`, whose Spec-BLOCK interception diverts to `autopilot-ticket.md` Step S instead (see `${CLAUDE_PLUGIN_ROOT}/context/spec-remediation.md`). Absent that interception — interactive `/build`, `/write-spec`, any other caller — the hard stop holds.
3. **Status precondition** is enforced by that flow's Step 1: if `status` is not `solution`, it stops and directs the lead to run `/problem XXXX` first. Honor that stop.
4. After the files are written, announce in one line: "No specs found — generated N spec(s)/task from `solution.md` (score-spec: PASS|WARN). Continuing to build."

Then load lead-curated context (both the specs-exist and just-generated paths):

**Standards gate (fail-closed).** Before the `@.tickets/_standards.md` include below, if `.tickets/_standards.md` exists, validate it first:

```
python3 "${CLAUDE_PLUGIN_ROOT}/validators/standards_validator.py" .tickets/_standards.md
```

A non-zero exit **halts** the build — show the validator's stderr (the missing or stubbed sections) and stop. This call runs **before** the `@.tickets/_standards.md` include, so stub content never enters context on a failing run.

If `.tickets/_standards.md` exists, load it via `@.tickets/_standards.md`.
If `.tickets/_learnings.md` exists, load it via `@.tickets/_learnings.md`.

Both are lead-curated. The model treats them as hard constraints, not suggestions. The machine's BM25 failure trail (`.harness/memory.db`) is consulted only by `memory(action="retrieve", ...)` during repair — it never feeds back into these files automatically.

**Spec-coverage warning (non-blocking).** Before executing specs, check whether any
requirement is left uncovered. If `spec-coverage.md` exists in the ticket directory,
invoke `spec_coverage.py --warning-only` as an **argument-list subprocess** (never a shell
string — no slug/path interpolation) and print its stdout if non-empty:

```python
import subprocess, sys
result = subprocess.run(
    [sys.executable, "spec_coverage.py", "--warning-only", ticket_dir_str, project_root_str],
    check=True,
    capture_output=True,
    text=True,
)
if result.stdout.strip():
    print(result.stdout)  # lists uncovered FRs/ACs
```

`--warning-only` reads the **pre-written** `spec-coverage.md` only — it does not re-parse
the spec files. The warning is **non-blocking**: print it (so the lead sees which FRs/ACs
have no covering spec) and then proceed with the build regardless. This check is
**backward compatible** — if `spec-coverage.md` does **not** exist (e.g. a ticket predating
the coverage map, or one whose specs were hand-written), skip it silently: no warning, no
error, no change in behavior.

## Step 1.9 — Dependency precondition (before worktree creation)

**Runs before the worktree is created/resumed in Step 2 — a fail-closed gate.** Read the
ticket's `depends-on:` field (see **Ticket dependencies** in
`${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`) and enforce it via `ticket_deps.py`,
scanning the filesystem **once** for this invocation:

```python
from pathlib import Path
from ticket_deps import parse_deps, blocking_dependencies

graph = parse_deps(Path(".tickets"))            # scans .tickets/ and .tickets/completed/ once
blocked = blocking_dependencies(graph, "XXXX")  # deps not yet in `done`
```

If `blocked` is non-empty, **stop before creating/resuming the worktree** and print a
structured error naming each blocking ticket and its current status, e.g.:

```
/build XXXX blocked — unresolved dependencies:
  - 0010 (implementing)
  - 0011 (review-ready)
Deliver those tickets (status: done) first, or edit this ticket's depends-on: field.
```

`parse_deps` also validates every `depends-on:` reference — a dependency on a ticket that
exists in neither `.tickets/` nor `.tickets/completed/` raises `ValueError` here (fail-closed).

## Step 2 — Resume the claim worktree (do not create one)

The branch `ticket/XXXX-<slug>` and worktree `.worktrees/XXXX-<slug>` already exist — they were created at claim time (`/problem` Phase 1), and the design artifacts live on the branch. **Resume** that worktree; do not fork a new one.

**Cycle check on every `status.md` write.** Each time this flow writes `status.md`
(`implementing`, `review-ready`, `changes-requested`), run a full-graph cycle check first so
an edit to any ticket's `depends-on:` cannot introduce a cycle that slips through:

```python
from pathlib import Path
from ticket_deps import parse_deps, assert_acyclic

assert_acyclic(parse_deps(Path(".tickets")))    # raises TicketCyclicDependencyError on a cycle
```

A `TicketCyclicDependencyError` (a `ValueError` subclass) names the full cycle path and
**rejects the write** — resolve the cycle before retrying.
 Only if the worktree is somehow absent (e.g. a fresh clone, or a ticket claimed before branch-at-claim) recreate it from the existing branch:

```
git worktree add .worktrees/XXXX-<slug> ticket/XXXX-<slug>   # fallback only — normally the worktree already exists
echo 'XXXX-<slug>' > .tickets/.active
```

Then transition `status: implementing` **on the branch** (branch only — it must **not** touch `main`), committing+pushing inside the worktree by running the helper from within it:

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX implementing --push   # cwd = .worktrees/XXXX-<slug>
```

Run with the worktree as the cwd so the helper resolves the worktree's `.tickets/` and commits to the branch; `--push` publishes the branch (setting upstream on first push).

From here, **all** implementation status churn (`implementing`, `review-ready`, `changes-requested`) is **branch only** — committed inside the worktree and pushed, never to `main`. `main` keeps showing `claimed` until `/deliver` squash-merges the branch.

## Step 3 — Load DAG and checkpoint

If a task file exists: call `dag_load("XXXX-<slug>", project_root)` to get execution layers.
If only spec files: treat each as a single-layer task.

Call `checkpoint(action="read", task_id="XXXX-<slug>", project_root=project_root)` — skip specs already completed.

Show the user the layers and any checkpoint-skipped specs.

## Step 4 — Execute each spec

For each spec in each layer (respecting DAG order):

**a. If already checkpointed** — skip with "✓ already passed".

**b. Load spec and context:**
```
spec_load(spec_id, project_root)
context_fetch(reference_files, target_file, project_root)
```
If upstream specs in this task have already been written to the worktree, include their implementations as additional context so downstream specs can reference the actual interfaces.

**c. Generate implementation and tests** in fenced code blocks (`# implementation` then `# tests`).

**d. Write to worktree:**
- Implementation → `worktree_dir / spec.target_file`
- Tests → appropriate test location (e.g. `worktree_dir/tests/test_<module>.py`)

If the target file already exists, integrate intelligently — don't overwrite unrelated content.

**e. Integration gate (directory mode):**

Call `gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root)`.

If it fails:
1. Call `memory(action="retrieve", errors_text=errors_text, gate=gate, project_root=project_root)`.
2. Fix the specific `file:line` locations in the worktree files directly.
3. **Repair-integrity check.** Before accepting the round, run the repair-integrity check on **this round's own diff** — the changes this repair attempt introduced, not the cumulative branch. Since the fixes here are still uncommitted, pass `git -C .worktrees/XXXX-<slug> diff` (the working-tree changes) through `classify_diff` in `gates/repair_integrity.py`. Do **not** diff against `main` — under concurrent delivery `main` advances and its new test functions would read as spurious removals. If the check reports any violation (a net removal of test functions, an added skip/xfail marker, or a net-new bare suppression pragma), the round **fails**: do not accept the green gate. Re-enter repair with the corrective instruction to **restore the test and fix the implementation** (or add a reason suffix to a genuinely justified suppression) rather than weakening the safety net.
4. Re-run `gate_run_on_dir`. Repeat up to `MAX_REPAIR_ATTEMPTS`.
5. If pass: call `memory(action="record", spec_id=spec_id, gate=gate, errors_text=errors_text, attempt=attempt, outcome="passed", project_root=project_root)`.
6. If still failing after `MAX_REPAIR_ATTEMPTS`: record the exhausted loop so future repairs are warned away from it — call `memory(action="record", spec_id=spec_id, gate=gate, errors_text=errors_text, attempt=attempt, outcome="escalated", project_root=project_root)` — then note the failure and continue to the next spec. (This mirrors the existing `outcome="passed"` record on success; retrieval surfaces both, marking escalated entries with `⚠`.)

**f. Checkpoint:**

Call `checkpoint(action="write", task_id="XXXX-<slug>", completed=updated_completed_list, project_root=project_root)`.

## Step 5 — Commit

```
git -C .worktrees/XXXX-<slug> add .
git -C .worktrees/XXXX-<slug> commit -m "feat: <short description from solution>"
```

Confirm the commit succeeds.

## Step 6 — Update status and show diff

Update `status.md` to `status: review-ready`. Commit it **in the worktree** (branch-local — it must not touch `main`):

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → review-ready"
```

Run and display:
```
git -C .worktrees/XXXX-<slug> diff main
```

Show a summary:
- Files changed, lines added/removed
- Which specs passed, which (if any) had integration failures

## Step 7 — Spawn post-build critic (automatic)

After the diff is shown, spawn the critic subagent (`critic`) with the following parameters:

- **Phase**: `code`
- **Ticket**: `XXXX-<slug>`
- **Round**: 1

The critic loads expert panels per the trigger table in `${CLAUDE_PLUGIN_ROOT}/skills/critique/SKILL.md` (driven by the worktree's file set), reads `gate-findings.md` if present, reads the worktree implementation + tests, reads `problem.md` / `requirements.md` / `solution.md` as the ticket baseline (for the requirements-coverage and solution-alignment checks in `critic-brief.md` Step 2.5), and produces structured BLOCKER / MAJOR / MINOR / OBS findings.

Display the critic's structured report to the user verbatim.

**Persist this round's report.** Append the critic's structured report to the ticket's `critic-findings.md` (the durable sibling of `gate-findings.md` — see "Critic findings file" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`), as a new append-only section headed by its round number and date:

```
## Round 1 — <today's date>

<the critic's structured report verbatim>
```

Then commit it on the branch (branch-local — it must **not** touch `main`):

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/critic-findings.md
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX critic findings round 1"
```

**Severity policy** (this is the core of the post-build loop):

- **BLOCKER and MAJOR findings are must-fix.** `/build` does **not** stop for the lead's decision on them — it auto-repairs them in the worktree (Step 7a). The lead is only consulted if auto-repair cannot clear them after `MAX_REPAIR_ATTEMPTS`.
- **MINOR and OBS findings are optional.** Never auto-fix them. List them for the lead to decide on (Step 7c).

### Step 7a — Auto-repair BLOCKER / MAJOR findings

**Dry-run suppression:** if this run is a dry run (`DRY_RUN=true`, i.e. reached via `build-dry-run-ticket.md`), the auto-repair loop does **not** run — evaluate `should_auto_repair(dry_run)` (from `dry_run.py`) at this entry point; it returns `False` under dry-run. The critic still runs in Step 7 and its findings are shown, but no repair commit is made and no worktree is touched. A dry run stops after displaying the critic output. This check is placed at Step 7a entry (not Step 7) so the critic always runs.

**If the critic surfaces no BLOCKER and no MAJOR findings**, skip to Step 7c.

Otherwise, enter the repair loop. Run up to `MAX_REPAIR_ATTEMPTS` (default 3) attempts:

For each attempt `N` (1 … `MAX_REPAIR_ATTEMPTS`):

1. Announce: "Auto-repair attempt N/`MAX_REPAIR_ATTEMPTS` — addressing M BLOCKER / K MAJOR finding(s)."
2. For each BLOCKER and MAJOR finding, fix the specific `file:line` location in the worktree files directly. Call `memory(action="retrieve", ...)` first when a finding overlaps a known failure pattern. Do **not** touch MINOR / OBS findings.
3. Re-run the integration gate so fixes don't regress: `gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root)`. If it fails, repair the gate failures (same inner loop as Step 4e) before proceeding — a green gate is a precondition for re-review.
3a. **Repair-integrity check.** Run the repair-integrity check on **this round's own diff** — the changes this repair round introduced. Capture the round's diff before its commit (`git -C .worktrees/XXXX-<slug> diff` on the still-uncommitted fixes, or `git -C .worktrees/XXXX-<slug> diff HEAD` if you staged them) and pass it through `classify_diff` in `gates/repair_integrity.py`. Do **not** diff against `main` — that is the cumulative branch diff against a moving tip and would re-flag earlier accepted changes and drift from concurrent deliveries. If it reports any violation (removed test functions, added skip/xfail markers, or net-new bare suppression pragmas), the round **fails**: re-enter repair with the instruction to **restore the test and fix the implementation instead** of silencing the gate. A green gate obtained by weakening the safety net does not count as repaired.
4. Commit the repair round: `git -C .worktrees/XXXX-<slug> commit -am "fix: address post-build critic round N findings"`.
5. Re-spawn the critic subagent (**Round**: `N+1`, same Phase/Ticket) to verify. Display its report verbatim. **Persist this round's report**: append it to `critic-findings.md` as a new append-only section headed by its round number and date (`## Round N+1 — <today's date>`), and commit that append on the branch alongside the round (`git -C .worktrees/XXXX-<slug> commit -am "chore(ticket): XXXX critic findings round N+1"`) — never touching `main`. See "Critic findings file" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`.
6. **If the new report has no BLOCKER and no MAJOR findings** → repair succeeded. Go to Step 7b.
7. **If BLOCKER / MAJOR findings remain** and attempts are left → loop to attempt `N+1`.

### Step 7b — Auto-repair succeeded

- Keep `status.md` at `status: review-ready`.
- Tell the user:
  > The post-build critic's BLOCKER/MAJOR findings were auto-repaired in N round(s) and re-verified clean. Options:
  > - Proceed to delivery with `/deliver XXXX`.
  > - For an interactive panel-aware re-review (e.g., to dig into remaining MINOR / OBS findings conversationally), run `/review XXXX`.
  > - For a comprehensive panel review of selected files, run `/critique <files>`.

### Step 7c — No must-fix findings (or only MINOR / OBS remain)

- Keep `status.md` at `status: review-ready`.
- Tell the user:
  > The post-build critic found no BLOCKER/MAJOR findings. Options:
  > - Proceed to delivery with `/deliver XXXX`.
  > - For an interactive panel-aware re-review (e.g., to dig into MINOR / OBS findings conversationally), run `/review XXXX`.
  > - For a comprehensive panel review of selected files, run `/critique <files>`.

### Step 7d — Auto-repair exhausted (ask the lead)

If BLOCKER / MAJOR findings still remain after `MAX_REPAIR_ATTEMPTS`:

- Update `status.md` to `status: changes-requested` and commit it in the worktree:
  ```
  git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
  git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → changes-requested"
  ```
- Show the lead the residual BLOCKER / MAJOR findings and what each repair round attempted.
- Tell the user:
  > Auto-repair could not clear N BLOCKER / K MAJOR finding(s) after `MAX_REPAIR_ATTEMPTS` attempts — your input is needed. Options:
  > - Advise on the approach, then run `/build XXXX` to resume repair with the existing worktree.
  > - Run `/review XXXX` for an interactive panel-aware deep-dive on the residual findings (same panels, conversational delivery, follow-up questions).
  > - For a comprehensive panel review against arbitrary files in the worktree, run `/critique <files>`.

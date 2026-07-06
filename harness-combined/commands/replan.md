Re-derive `solution.md` from the current `problem.md` and `requirements.md` for an already-designed ticket, run the critic loop, present a diff, and commit — the supported path to refresh a stale solution after requirements shift.

> When this overwrites `solution.md`, the `pre_ticket_diff` hook automatically prints a unified diff of the pending change before the write (set `HARNESS_NO_DIFF=1` to suppress). The explicit diff in Step 7 is in addition to that hook — it is the lead-facing review artifact.

Unlike `/refine` (which edits `solution.md` in place, conversationally), `/replan` regenerates it from scratch from the two upstream artifacts. Use `/replan` when `requirements.md` has changed enough that an incremental edit no longer captures the design; use `/refine` for targeted touch-ups. This command operates on `main` — it does not create a worktree of its own.

## Usage

```
/replan XXXX
```

- `XXXX` — a ticket number (bare four digits `0033` or number-with-slug `0033-replan-command`; the slug is ignored).

## Ticket Resolution

If a ticket number is provided, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found — the same lookup convention as every other command. If the argument is empty or resolves ambiguously to multiple ticket directories, list the candidates and require the lead to specify one before continuing. If no ticket matches, stop and report.

## Step 1 — Status guard (fail-closed)

Read the resolved ticket's `status.md`. `/replan` regenerates a solution, so it is only valid where a `solution.md` is expected to exist. Accept only these statuses:

- `solution`
- `implementing`
- `review-ready`
- `changes-requested`

**Reject** any other status. The `requirements` and `problem` statuses are explicitly excluded (no solution has been designed yet) — stop with a clear error directing the lead to run `/problem XXXX` to reach `status: solution` first. (NFR-2 covers the edge case where the status is valid but `solution.md` was never committed — the snapshot in Step 4 handles that with an empty fallback; the guard itself is purely status-based.)

Record the **prior status** now — Step 8's commit message encodes it when it differs from `solution` (a rollback).

## Step 2 — Worktree guard (Checkpoint-style confirmation)

Detect whether a worktree for this ticket exists:

```
git worktree list | grep "ticket/XXXX-<slug>"
```

**If a worktree is present**, in-progress implementation may **diverge** from the replanned solution — regenerating `solution.md` (and, for `implementing`/`review-ready`, rolling `status` back to `solution`) can invalidate the specs and code already produced in that worktree. Warn the lead explicitly, naming the worktree path, and present a **Checkpoint-style prompt** — never a bare stdin `read`, which is unavailable in the harness interaction context:

```
## Replan will diverge from in-progress work

Ticket XXXX has an active worktree at .worktrees/XXXX-<slug> (branch ticket/XXXX-<slug>).
Replanning regenerates solution.md and may roll status back to `solution`, invalidating
the specs/code already built there. After replanning you must reconcile that worktree
before resuming — remove and rebuild it:

    git worktree remove .worktrees/XXXX-<slug>
    /build XXXX        # re-run from the replanned solution

The commit lands on `main` while the branch is ahead; rebase or merge before the next /build.

Proceed? (yes/no)
```

Wait for an **explicit `yes`**. On `no` (or any non-`yes` response), abort without touching any file. **If no worktree exists**, skip this prompt and continue.

## Step 3 — Read the upstream artifacts (read pass)

Read `problem.md` and `requirements.md` **in full** from the resolved ticket directory. These are the sole inputs to regeneration. This is a distinct **read pass** that completes before the write pass in Step 5 — the trust-boundary control from `solution.md`: the model ingests the artifact text without holding solution-write access in the same turn. `problem.md` is read-only context here (per the ticket's Out of Scope, `/replan` never modifies it).

## Step 4 — Snapshot the current solution (in-memory)

Capture the current `solution.md` into a shell variable via `git show` — no filesystem write, so there is no temp-file or partial-write risk:

```
snapshot=$(git show HEAD:.tickets/XXXX-<slug>/solution.md 2>/dev/null || true)
```

The `2>/dev/null || true` is the **empty-snapshot fallback**: if `solution.md` was never committed (a valid-status ticket whose solution does not exist yet — NFR-2), `git show` fails and `snapshot` is empty. That is not an error — Step 7's diff simply shows the full new file as added, with a note that there was no prior solution. Capturing the last *committed* version (not local edits) is intentional: the harness requires ticket artifacts to be committed after every transition, so uncommitted `solution.md` edits represent an erroneous state.

## Step 5 — Regenerate the solution (write pass)

Regenerate `solution.md` **from scratch** from the `problem.md` and `requirements.md` read in Step 3, mirroring the structure and constraints of **`/problem` Phase 4** exactly: the standard sections — `## Approach`, `## Components`, `## Tech Choices`, `## Test Plan`, `## Tradeoffs`, `## Risks`, `## Implementation Order` — and the same 80-line hard limit. Every functional requirement must appear as a row in the Test Plan table (this is what keeps the output idempotent under NFR-1: identical `requirements.md` yields the same structural contract, modulo LLM non-determinism in prose).

**LLM observability (hard constraint).** The regeneration is an LLM invocation. Before writing `solution.md`, log the rendered **prompt**, the full model **response/output**, and any **tool calls** made during regeneration — per the CLAUDE.md "Observability for LLM calls" rule. The trace is emitted first, then the file is written.

**Fail-closed write.** The write to `solution.md` is conditional on receiving a **non-empty, structurally valid** regenerated solution (contains the required sections above). If regeneration fails — network/model error, context overflow, or an empty/malformed response — **abort before overwriting**: do **not** write a partial file, do **not** commit, and report the failure. Partial writes are never committed. The prior `solution.md` on disk is left untouched on abort.

## Step 6 — Critic loop (max 2 rounds)

Run the critic loop on the regenerated `solution.md`, using the same protocol as `/problem` Phase 5. **The cap is 2 rounds, stated here inline and not delegated by reference** — so this command's behavior stays fixed even if `/problem` Phase 5 changes.

Spawn the **critic subagent** (`subagent_type: critic`) with a design-phase brief (Phase: **design**, Ticket: **XXXX-<slug>**, Round: **1**), following `${CLAUDE_PLUGIN_ROOT}/context/critic-brief.md`. Revise `solution.md` based on its findings.

- **Round 2 fires only if a BLOCKER remains** after the round-1 revision. If round 1 surfaced no BLOCKER, stop at one round.
- **Maximum 2 rounds.** Do not spawn a third round regardless of residual findings — carry any remaining MINOR/OBS notes forward in the solution's Open Questions or Risks.

## Step 7 — Present the diff

Produce and display a unified diff of the snapshot (Step 4) versus the regenerated file. Use `git diff --no-index`, capturing output separately from the exit code — exit 1 (files differ) is the **normal** case, not an error:

```
diff_output=$(git diff --no-index <(echo "$snapshot") .tickets/XXXX-<slug>/solution.md || true)
```

Display `diff_output` to the lead. **If the old and new content are identical** (empty diff — LLM reproduced the prior solution, or the empty-snapshot case produced nothing to compare), show an explicit **"no changes"** notice rather than a blank diff, so the lead knows the run completed and nothing changed. When the snapshot was empty (no prior solution), note that the entire file is new.

## Step 8 — Update status and commit

Update `status.md`: set `status: solution` and the `updated` field to today's date. For a ticket already at `solution` this is a refresh; for `implementing`/`review-ready`/`changes-requested` this is a **rollback** to `solution` (the design decision below).

Commit the revised `solution.md`, `status.md`, and `requirements.md` to `main` in a **single commit** after the critic loop completes:

```
git add .tickets/XXXX-<slug>/solution.md .tickets/XXXX-<slug>/status.md .tickets/XXXX-<slug>/requirements.md
git commit -m "chore(ticket): XXXX replan (status: solution)"
```

- **Normal refresh** (prior status was `solution`): use the message above verbatim — `chore(ticket): XXXX replan (status: solution)`.
- **Rollback-aware form** (prior status was `implementing`, `review-ready`, or `changes-requested`): encode the prior status so the git log distinguishes a rollback from a refresh, e.g. `chore(ticket): XXXX replan (status: solution ← implementing)`. Naming the prior status makes the rollback a searchable domain event in history.

After committing, if a worktree exists (the lead confirmed `yes` in Step 2), restate that it must now be reconciled — remove and re-run `/build XXXX` — before resuming, and that the branch is ahead of `main` and needs a rebase or merge first. Running `/build` on the stale worktree after a replan is unsafe.

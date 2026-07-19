# Design: Relocate ticket coordination to a dedicated `.harness-tickets` branch

**Date:** 2026-07-19
**Status:** Proposed (Checkpoint 1 pending)
**Author:** Bradley + Claude

## Problem

Today `main` carries **two commits per ticket**: the `claimed` stub (a
git-coordinated, first-push-wins number claim) and the squashed delivery
(`harness-reference.md` "Two commits on `main`"). The claim stub is doing double
duty: it is both the *number-allocation arbiter* (its presence reserves the number)
and a coarse status signal other developers read off `main`.

That coupling has costs:

- `main` accrues a `chore(ticket): XXXX claim` commit for every ticket the moment
  design starts — before any reviewed work exists, and even for tickets later
  cancelled or abandoned. `main`'s history interleaves coordination churn with
  product history.
- Number allocation depends on scanning `.tickets/*` on `main`
  (`ticket.py: next_number`), so the "what number is next" question is answered by
  `main`'s working tree rather than a purpose-built ledger.
- Cancelled/abandoned tickets still write terminal commits to `main` for work that
  never merged.

## Goal

Move all pre-merge ticket coordination — number allocation and the claim record —
off `main` and onto a dedicated **`.harness-tickets`** branch. After this change:

- **`main` receives exactly one commit per delivered ticket: the squash merge.**
  Nothing a ticket writes touches `main` until its feature branch merges.
- **Number allocation reads/writes `.harness-tickets`**, which is the
  authoritative counter + registry.
- The feature branch continues to carry the *full* ticket contents
  (`problem.md` / `requirements.md` / `solution.md` / specs / `status.md` /
  implementation) — as it already does today; that half of the model is unchanged.

## Non-goals

- Changing the design→build→deliver *workflow* stages or the critic loops.
- Changing where in-flight ticket **content** lives (already branch-only).
- A server/database coordinator. Coordination stays git-native (first-push-wins),
  just on a dedicated ref instead of `main`.

## What is already true (and therefore unchanged)

The current model already satisfies "each feature branch has the full contents of
its ticket": Phases 2–4 of `/problem` write every artifact into the worktree on
the branch and push there; only the *claim stub* lives on `main` pre-delivery
(`problem.md` Phase 1, `harness-reference.md:123`). So this design does **not**
introduce branch-local ticket content — it removes the one remaining `main`
touchpoint (the claim) and relocates its coordination role.

## Design

### 1. The `.harness-tickets` branch (orphan, never merged)

An **orphan** branch (no shared history with `main`) holding coordination state
only — never product code, and **never merged into `main`**. Contents:

```
.harness-tickets (orphan)
  ledger.jsonl      # append-only lifecycle log — the source of truth
```

`ledger.jsonl` is append-only, one JSON object per line:

```json
{"event":"claim","number":59,"slug":"foo-bar","title":"…","owner":"a@b.c","branch":"ticket/0059-foo-bar","ts":"…"}
{"event":"delivered","number":59,"sha":"<main squash sha>","ts":"…"}
{"event":"cancelled","number":60,"ts":"…"}
```

- **Next number** is derived: `max(number over all claim events) + 1`. No separate
  counter file to keep in sync.
- **Append-only** is deliberate: first-push-wins serializes writers, and an append
  log never produces the line-level conflicts a rewritten JSON array would. It also
  yields a free audit trail (who claimed what, when, what was cancelled).
- Coarse lifecycle events only: `claim`, `delivered`, `cancelled`, `abandoned`,
  `reopened`. Fine in-flight status (`implementing` / `review-ready` /
  `changes-requested`) stays **branch-only and authoritative in the worktree**,
  exactly as today — this preserves the current coarse/fine split and keeps the
  ledger contention-free (only lifecycle boundaries write to it).

### 2. Claim becomes a `.harness-tickets` transaction

`ticket.py: claim` changes from "commit stub to `main`, push first-wins" to:

1. `git fetch origin .harness-tickets` (create locally if absent — see §6).
2. Read `ledger.jsonl`; compute `number = max(claim.number) + 1`.
3. Append a `claim` event; commit on `.harness-tickets`; **push first-wins**.
   - On a non-fast-forward rejection, another writer claimed concurrently:
     re-fetch, recompute `number`, re-append, retry (bounded, exponential backoff —
     mirrors the current 5-retry renumber loop).
4. **Only after the winning ledger push** (create-after-push, unchanged principle):
   create branch `ticket/XXXX-<slug>` off `main` HEAD and worktree
   `.worktrees/XXXX-<slug>`, and write the `status: claimed` stub **on the branch**
   (`.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/status.md`). **No `main` commit.**

The arbiter moves from "the claim commit on `main`" to "the claim line in
`.harness-tickets`"; the first-push-wins guarantee is identical, just on another
ref. `next_number` reads the ledger, not `.tickets/*` on `main`.

Accessing `.harness-tickets` without disturbing the working tree: the helper uses
an **ephemeral linked worktree** (`git worktree add <tmp> .harness-tickets` →
append → commit → push → `git worktree remove`), or git plumbing
(`git show origin/.harness-tickets:ledger.jsonl` to read; `commit-tree` +
`update-ref` + push to write). Ephemeral worktree is simpler and matches the
codebase's worktree-centric patterns; plumbing is more concurrency-robust. Choice
flagged for Checkpoint 1.

### 3. Delivery is the only `main` commit

`deliver_squash` / `deliver_squash_batch`:

1. `git merge --squash` the feature branch → **one commit on `main`** with the
   entire branch diff (code + the branch's ticket docs), folding the `→ done`
   transition and the `completed/<slug>/` archive into that same commit (Option 1 —
   see §5). This is now the *first and only* time `main` sees the ticket.
2. Append a `delivered` event (with the squash SHA) to `.harness-tickets`; push.
3. Remove the worktree, delete the branch.

Push order: `main` first (the durable product record), then the ledger append. If
the ledger push loses a race, re-fetch and re-append — the append is idempotent by
`(event, number)` and `main` is already correct, so reconciliation never blocks
delivery. The merge-base story is *simpler* than today: because `main` never held a
claim stub, the branch's `.tickets/<slug>/` is a pure addition at squash time — no
stale stub to reconcile.

### 4. Cancel / abandon / reopen become `main`-free (pre-merge)

A cancelled or abandoned ticket never merged, so under "nothing to `main` until
merge" its docs must not land on `main`:

- **Cancel / abandon**: append `cancelled` / `abandoned` to `.harness-tickets`;
  delete the branch + worktree; archive the ticket docs onto `.harness-tickets`
  (see §5) rather than committing a terminal archive to `main`. This *removes* the
  terminal `main` commit these paths write today.
- **Reopen**: fork a fresh branch off `main` HEAD, restore the ticket dir from its
  archive (main's `completed/` for a delivered ticket under Option 1, or
  `.harness-tickets` for a cancelled one), append a `reopened` event, set
  `status: solution` on the branch.

### 5. Where delivered/cancelled ticket **docs** live — the one real decision

- **Option 1 (recommended, faithful to "the merge brings everything"):** the
  delivery squash carries the branch's ticket docs to `main`, archived into
  `completed/<slug>/` in that same commit — as today, minus the pre-delivery
  claim/status commits. Cancelled/abandoned docs (never merged) archive onto
  `.harness-tickets`. `main` = product code + delivered ticket docs; `main` history
  is clean of coordination churn.
- **Option 2 (full separation):** the delivery squash carries **only code**; all
  ticket docs (delivered and cancelled alike) live on `.harness-tickets`. `main`
  becomes pure product code. Cleaner separation, but delivered commits on `main` no
  longer carry their own problem/solution rationale inline with the code.

Recommendation: **Option 1.** "Nothing to `main` until merged" is about *timing*
(no pre-merge commits), which Option 1 satisfies, while keeping delivered rationale
co-located with the code that shipped it. Option 2 is a clean variant if `main`
should be code-only.

### 6. Bootstrapping and migration

- **`/init`**: if `origin/.harness-tickets` is absent, create the orphan branch
  (`git checkout --orphan`, clear the index, write an empty `ledger.jsonl`, commit,
  push), then return to the prior branch. Fresh clones `git fetch` it on first
  ticket op.
- **Migration** (one-time, from the current state): seed `ledger.jsonl` by scanning
  the existing `.tickets/*` (in-flight 0053–0058) and `.tickets/completed/*` on
  `main` — emit a `claim` event per ticket and a `delivered`/`cancelled` event for
  terminal ones — then push `.harness-tickets`. `next_number` seeds from the
  existing max. Existing `main` claim stubs stay as history; the helper simply
  stops writing new ones. No rewrite of `main` history.

### 7. Invariants and guards

- **`.harness-tickets` must never merge into `main`.** Add a guard in the deliver
  path (and optionally a `pre_merge` hook) that refuses any merge whose source is
  `.harness-tickets`.
- **`main` must carry no in-flight `.tickets/XXXX-<slug>/` dir** — only
  `completed/` (Option 1). A guard asserts the working tree has no non-completed
  ticket dir staged for a `main` commit.
- **`ticket_commit_guard` (Stop hook)** extends: a claim is incomplete unless its
  `.harness-tickets` ledger line was pushed *and* the branch stub committed — block
  the turn on a half-claim. It still scans every worktree for uncommitted
  branch-only ticket dirs (unchanged).

## Consequence: cross-cutting queries change their source of truth

This is the largest ripple and must be done alongside the helper change, or these
surfaces silently see zero in-flight tickets:

| Surface | Today | After |
|---|---|---|
| `ticket.py: next_number` | scan `.tickets/*` on `main` | `max(claim.number)+1` from `ledger.jsonl` |
| `/ticket-status` | list `.tickets/*` on `main` | ledger in-flight (claim w/o terminal) + local worktrees for fine status |
| `skills/sprint/compute.py`, `stale`, `velocity` | enumerate `.tickets/*` on `main` | enumerate from ledger; join branches/worktrees for fine status |
| `autopilot-batch` / `autopilot-ticket` | claim via `main`; batch-deliver to `main` | claim via `.harness-tickets`; batch deliver = the atomic `main` commit(s) |

For a remote in-flight ticket owned by another dev, fine status is read from its
pushed branch (`git show ticket/XXXX-<slug>:.tickets/XXXX-<slug>/status.md`); the
ledger supplies the coarse `claimed` state and the branch name to look it up.

## Files to change

Engine:

1. `ticket.py` — `next_number` (read ledger); `claim` (ledger transaction +
   create-after-push, no `main` commit); `deliver_squash` /
   `deliver_squash_batch` (single `main` commit + `delivered` ledger append);
   cancel/abandon/reopen paths (`main`-free, ledger events); new
   `ledger_read` / `ledger_append` / `ensure_tickets_branch` + the
   `.harness-tickets` access layer (ephemeral worktree or plumbing).
2. `hooks/ticket_commit_guard.py` — half-claim detection; the never-merge and
   no-in-flight-on-`main` guards (or a new `hooks/pre_ticket_merge.py`).

Prompt/flow (project-root copies, per `CLAUDE.md`):

3. `commands/problem.md` — Phase 1 rewrite: claim targets `.harness-tickets`;
   branch off `main`; stub on branch; no `main` commit.
4. `context/harness-reference.md` — replace "Two commits on `main`" with "One
   commit on `main` (delivery only); coordination on `.harness-tickets`"; update
   the status-table **commit-target** column (claimed → `.harness-tickets`);
   document the ledger and its invariants.
5. `context/flows/deliver-ticket.md`, `commands/deliver.md` — delivery is the sole
   `main` commit + ledger `delivered` append.
6. `commands/cancel.md`, `commands/abandon.md`, `commands/reopen.md` — `main`-free
   terminal handling via the ledger.
7. `context/flows/autopilot-batch.md`, `autopilot-ticket.md` — claim/deliver via
   the new coordination path.
8. `commands/ticket-status.md`, `skills/sprint/compute.py`, `skills/stale/SKILL.md`,
   `skills/velocity/*` — read the ledger.
9. `commands/init.md` — bootstrap the orphan branch.

## Verification

Engine tests (`tests/`, mirroring `test_ticket_archiving.py`):

1. **Number race:** two concurrent `claim` calls against the same
   `.harness-tickets` HEAD produce **distinct** numbers; the loser re-fetches and
   renumbers; both branches/worktrees are created only after their winning push.
2. **`main` stays clean pre-delivery:** through claim → design → build →
   review-ready, `git log main` shows **no** new commit for the ticket; the ledger
   shows the `claim`; the branch shows the full ticket dir.
3. **Delivery is one commit:** `/deliver` yields exactly one new `main` commit
   containing code + `completed/<slug>/` (Option 1), and one `delivered` ledger
   line with that SHA.
4. **Cancel is `main`-free:** `/cancel` adds no `main` commit; ledger shows
   `cancelled`; branch/worktree removed; docs recoverable for `/reopen`.
5. **Bootstrap + migration:** `/init` on a repo without `.harness-tickets` creates
   the orphan branch; migration seeds the ledger from existing `.tickets/*` and
   `completed/*`; `next_number` continues the sequence without collision.
6. **Guard:** an attempt to merge `.harness-tickets` into `main`, or to stage an
   in-flight `.tickets/XXXX/` dir onto `main`, is blocked.

## Open decisions for Checkpoint 1

1. **Doc placement:** Option 1 (delivered docs → `main` `completed/`) vs Option 2
   (`main` code-only, all ticket docs on `.harness-tickets`). Recommend 1.
2. **Ledger shape:** append-only `ledger.jsonl` (recommended) vs a rewritten
   registry JSON + `NEXT` counter.
3. **`.harness-tickets` access:** ephemeral linked worktree (simple) vs git
   plumbing (more concurrency-robust).
4. **Ledger richness:** coarse lifecycle only (recommended — low contention) vs
   mirroring in-flight `implementing`/`review-ready` for zero-branch-peek remote
   status.
5. **Migration timing:** fold into `/init`, or a one-shot `ticket.py migrate`
   invoked once against the current 0053–0058 + completed set.

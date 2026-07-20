# Flow: autopilot — batch mode

Autonomous build-to-deliver pipeline for **two or more related tickets built into
one integration worktree, tested together, and delivered in a single atomic push**
(one squashed commit per member). Reached only from `/autopilot` when `$ARGUMENTS`
names two or more ticket IDs; a single ID uses `autopilot-ticket.md` unchanged.

Every member has been confirmed at `status: solution`.

**Announce**: "Autopilot batch mode for XXXX + YYYY + ZZZZ (lead: XXXX-slug)."

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). This is the parent run; the per-member `build-ticket.md` sub-flows adopt this same list:

`Create integration worktree · Build members in order · Combined critic + auto-repair · Batch deliver (1 push) · Cleanup`

## Step 0 — Resolve members, order, and lead

`$ARGUMENTS` is a whitespace-separated list of 4-digit IDs. For each ID, resolve `.tickets/<id>*/` (do **not** fall back to `completed/` — a member must be live), read `status.md`, and record `slug`, `title`, and `branch` (`ticket/XXXX-<slug>`).

- **Every member must be at `status: solution`.** If any is not, stop and list the offenders: "Batch aborted — these members are not at `status: solution`: …. Run `/problem` on them or drop them from the batch."
- **Refine-touched exclusion.** For each candidate member, probe its own ticket
  branch for a persisted `/refine` marker: `git show
  ticket/XXXX-<slug>:.tickets/XXXX-<slug>/refine-touched.md`. A present marker
  means that member's design scope was machine-adjusted by a `/refine` pass and
  must not silently join an atomic batch delivery — exclude that member and
  report it to the lead: "Excluded from batch — refine-touched: XXXX-slug. Deliver
  it individually via `/autopilot XXXX` (Step B's confirmation carve-out applies)."
  Apply this exclusion **before** requiring ≥ 2 members below, so the count check
  reflects the post-exclusion membership.
  - **Exactly 1 member remains** after exclusion → do not proceed with batch Steps
    1+; instead run `autopilot-ticket.md` (single-ticket mode) on that one
    remaining member.
  - **0 members remain** → stop and report every excluded member; do not create
    the integration worktree.
- Require **≥ 2** distinct members (after refine-touched exclusion). If only one
  resolves, tell the lead to use plain `/autopilot XXXX` and stop.

**Build order.** There is no cross-ticket dependency graph in the harness, so default to the order the IDs were given; if the lead gave no meaningful order (e.g. reverse), fall back to ascending ticket number. State the resolved order in one line. The **lead** is the first member in build order; its slug names the batch branch/worktree (`batch/<lead-slug>`, `.worktrees/batch-<lead-slug>`).

## Step 1 — Create the integration worktree

`main` is untouched by any in-flight member — each member's number claim lives on the `harness-tickets` ledger, and its `claimed` stub + design artifacts live on its `ticket/XXXX-<slug>` branch. The batch delivery (Step 5, one atomic push) is the first time `main` sees these tickets, and it also appends one `delivered` ledger event per member. Fork a fresh integration worktree from `main` and set the batch sentinel:

```
git worktree add .worktrees/batch-<lead-slug> -b batch/<lead-slug> main
echo 'batch-<lead-slug>' > .tickets/.active
```

## Step 2 — Build each member into the integration worktree (in order)

For each member **in build order**, do the following inside `.worktrees/batch-<lead-slug>`:

1. **Import the member's design artifacts** from its ticket branch onto the batch branch (so the build's inline spec generation has `solution.md` to work from):
   ```
   git -C .worktrees/batch-<lead-slug> checkout ticket/XXXX-<slug> -- .tickets/XXXX-<slug>/
   git -C .worktrees/batch-<lead-slug> add .tickets/XXXX-<slug>/
   git -C .worktrees/batch-<lead-slug> commit -m "chore(batch): import XXXX design artifacts"
   ```
2. **Build the member** by following `${CLAUDE_PLUGIN_ROOT}/context/flows/build-ticket.md` under its **batch-mode override** (see the override callout in that flow): write into `.worktrees/batch-<lead-slug>`, run the integration gate there, commit the member's build as `feat: XXXX <desc>` on the batch branch, and **skip Step 2 (worktree), Step 6's status commit, and Step 7 (per-ticket critic)**.
3. **Record the member's delivery boundary** — the batch-branch rev after its build commit:
   ```
   git -C .worktrees/batch-<lead-slug> rev-parse HEAD
   ```
   Keep an ordered list of `{slug, title, head}` (the member-boundary map).

If a member's integration gate cannot go green after `MAX_REPAIR_ATTEMPTS`, **stop the whole batch** and go to Step 4 (no partial delivery).

## Step 3 — Combined critic over the union + auto-repair

With every member built into the one worktree, the tree is the true integration state. Run the gate once more over the whole worktree, then spawn **one** critic subagent (`critic`, Phase `code`, Round 1) over the union of all member changes. Follow the same severity policy and auto-repair loop as `build-ticket.md` Steps 7/7a (up to `MAX_REPAIR_ATTEMPTS`), committing each repair round on the batch branch.

- Repairs land **after** the last member's boundary, so they fold into the last member's delivery commit. After repairs settle, **update the last member's `head`** in the member-boundary map to the current batch HEAD:
  ```
  git -C .worktrees/batch-<lead-slug> rev-parse HEAD
  ```
- **If the critic clears (no BLOCKER/MAJOR)** → go to Step 5.
- **If auto-repair exhausts** → go to Step 4.

Members touched by a `/refine`-style semantic scope change are out of scope for autopilot batch — this flow only auto-delivers clean, mechanically-repaired builds.

## Step 4 — Batch repair exhaustion (stop, no partial delivery)

A batch is atomic: if any member cannot be cleared, none deliver. Do **not** deliver a subset.

1. Leave the integration worktree and batch branch intact.
2. Transition **each** member's `status.md` to `changes-requested` on its own `ticket/XXXX-<slug>` branch (branch-only — never `main`), committing+pushing per member via `ticket.py set-status XXXX changes-requested --push` run from that member's worktree.
3. Show the residual BLOCKER/MAJOR findings and tell the lead:
   > Autopilot batch could not clear all BLOCKER/MAJOR findings after full auto-repair. The integration worktree `.worktrees/batch-<lead-slug>` is intact. Options:
   > - Fix in the integration worktree, then re-run `/autopilot XXXX YYYY …`.
   > - Run `/review` on a specific member for an interactive deep-dive.

Then stop.

## Step 5 — Batch deliver (one atomic push, one commit per member)

Show the union diff (informational — not a gate):

```
git -C .worktrees/batch-<lead-slug> diff main
```

Then deliver from the main repo root (working tree clean, on `main`). Write the member-boundary map to a transient JSON file and hand it to the batch delivery helper — encapsulated and unit-tested as `ticket.py deliver_squash_batch()`:

```
# members.json = [{"slug":"XXXX-<slug>","title":"…","head":"<rev>"}, … in build order,
#                  last member's head = batch HEAD after repairs]
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" deliver-batch batch/<lead-slug> .tickets/.batch-<lead-slug>.json
rm -f .tickets/.batch-<lead-slug>.json
```

The helper cherry-picks each member's cumulative range as one squashed `feat: XXXX <title> (squash)` commit (folding that member's `completed/XXXX-<slug>/` archive at `done`), publishes all commits in **one** push, and — only on a successful push — removes the batch worktree/branch **and** every member's vestigial `ticket/XXXX-<slug>` branch and `.worktrees/XXXX-<slug>` worktree. On a cherry-pick conflict or rejected push it raises with everything intact; surface the error and stop (the lead rebases and re-runs).

Because the whole batch is one push, **no member ever rebases another mid-delivery** — the `deliver-ticket.md` Step 7 sibling-rebase churn does not occur for batch members.

## Step 6 — Clear sentinel and report

```
rm -f .tickets/.active
```

Then rebase any *other* in-flight (non-batch) worktrees onto the new `main` following `deliver-ticket.md` Step 7, and summarize: the N squashed commits added (one per member), the single push, and what was cleaned up.

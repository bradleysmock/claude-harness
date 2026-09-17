# Human in the Loop

Part 5 of the design series. See [00-overview.md](00-overview.md) for the pipeline this sits on top of, [01-gates-and-hooks.md](01-gates-and-hooks.md) for the gate mechanics that generate most escalations, and [02-commands-and-skills.md](02-commands-and-skills.md) for the commands referenced throughout.

Every other document in this series describes what the harness does on its own. This one describes the opposite question: where a human is required, what makes the machine hand control back, and how much autonomy a lead can dial in or out for a given piece of work.

---

## The two hard checkpoints

Per the working agreement (`CLAUDE.md`), the lead has final say at exactly two points, regardless of how autonomous the rest of the run is:

1. **Checkpoint 1 — design approval.** After `/problem` writes `problem.md` / `requirements.md` / `solution.md` and the design-phase critic has run its rounds, the lead reviews a concise summary ("what was decided, what the critic found, what changed") and approves or sends it back. Approval is a specific, checkable fact, not a vibe: the lead's "yes" stamps `approved-commit` — the branch HEAD *before* that write — onto `status.md`. Everything downstream that's allowed to build without asking again (`/build`, `/autopilot`, `autopilot-watch`) re-verifies this signal by diffing the design files between that SHA and the branch's current HEAD; any later edit without a fresh approval is treated as unapproved and never built.
2. **Post-build diff review.** After `/build` completes — gates green, critic's BLOCKER/MAJOR findings cleared, craft polish converged — the lead reviews the diff before `/deliver`. This is where `/review XXXX` (interactive, conversational) or `/critique <files>` (free-form, comprehensive) get used if the automatic post-build critic's one-shot report isn't enough.

Communication norms follow directly from this: the harness does **not** narrate intermediate steps during an autonomous phase. It reports at the checkpoint, surfaces blockers the moment they're found, and otherwise stays quiet — the two checkpoints are the two moments a lead's attention is actually needed, and everything in between is deliberately not competing for it.

---

## The control spectrum

The same pipeline runs at five different levels of hands-on-ness. Moving right trades granular control for throughput; every level still respects the escalation triggers in the next section — autonomy changes *how much you're asked*, never *whether a genuine problem gets surfaced*.

| Level | Invocation | What the human does | What still escalates |
|---|---|---|---|
| **Manual, phase by phase** | `/requirements`, `/solution`, `/refine`, `/replan` run individually | Reviews and edits after every single phase | N/A — nothing is unattended |
| **Manual, full design + build** | `/problem XXXX` then `/build XXXX` | Approves at Checkpoint 1, reviews the diff before `/deliver` | Repair-loop exhaustion, critic exhaustion, score-spec BLOCK |
| **Single-ticket autopilot** | `/autopilot XXXX` | Approves at Checkpoint 1 only; build → deliver runs unattended | All of the above, plus scope-drift confirmation if `/refine` touched the design mid-build |
| **Watched autopilot** | `/autopilot-watch start` running in the background | Approves at Checkpoint 1 for each ticket, whenever convenient; the watcher dispatches `/autopilot` automatically once it sees a verified approval | All of the above, plus the watcher's own fail-closed approval-drift check |
| **Batch autopilot** | `/autopilot 0012 0013 0014` | Approves each ticket's design beforehand; delivery is atomic across the batch | All of the above, at the batch level — one member's repair exhaustion blocks the whole batch's delivery, not just its own |

Two flags shift a given run along this spectrum without changing which command you type:

- **`--dry-run`** (`/build XXXX --dry-run`, ticket mode only) — runs the design-phase critic and the gate suite in a sandboxed temp directory, writes nothing but `gate-findings.md`, and never touches a worktree. A look-before-you-leap lever for a lead who wants to see what a build *would* do before committing to it.
- **`--pr`** (`/deliver XXXX --pr`, ticket mode only) — inserts a GitHub PR review step between the branch and `main` instead of merging directly. Useful when a change needs a second pair of human eyes beyond the lead who ran the pipeline, or when org policy requires PR review regardless of what the harness already checked.

---

## Escalation mechanics: what actually hands control back

These are the concrete, mechanical triggers — not vibes, not "the model decided to ask" — that stop an autonomous run and put a decision in front of a human. Each one is a specific piece of Python logic, consistent with the harness's rule that verdicts are computed, not judged.

### Repair-loop exhaustion → `changes-requested`

The post-build critic's BLOCKER and MAJOR findings are must-fix: `/build` auto-repairs them and re-spawns the critic to verify, looping up to `MAX_REPAIR_ATTEMPTS` (default 3, configurable in `.harness/config.py`). Only when that budget is exhausted does the ticket get set to `status: changes-requested` and the lead is asked for input — never after the first failed attempt. The critic's `finding_key` reconciliation (see [01-gates-and-hooks.md](01-gates-and-hooks.md)) tracks fixed/persisted/new across rounds so the lead-facing report at exhaustion says exactly what's still wrong, not just "still failing."

### Gate policy → `pause_for_human`

The data-driven promotion policy (`gates/policy.py`) can classify a gate outcome as `"promote"`, `"block"`, or `"pause_for_human"` per the `[policy]` block in `_standards.md` — a lead can mark a specific gate as one that should stop and ask rather than auto-block or auto-promote. On `pause_for_human`, the calling flow records the escalation in `.harness/memory.db` (`outcome="escalated"`), prints the same lead-facing options framing the repair-exhaustion path uses, and leaves `status.md` untouched — a flow-level halt, not a status transition, so nothing about the ticket's recorded state implies more happened than actually did.

### Score-spec BLOCK

Before a ticket builds, a score-spec validation pass can return a `BLOCK` on the design. What happens next depends on the control level: in **manual mode**, this bounces straight to the lead. In **autopilot mode**, `autopilot-ticket.md` Step S first attempts a bounded auto-remediation — a mechanical fix pass (`gates/spec_remediate.py`, text substitutions and test-plan row edits only, never touching FR prose) and, if that's not enough, at most one `/refine` pass constrained to deriving fixes from existing artifact text. Only if *that* is exhausted does Step A escalate to the lead with the same repair-exhaustion framing. Critically: if the `/refine` pass touched design scope (as opposed to the purely mechanical fix), a `refine-touched` marker is written — this forces a delivery confirmation later even under autopilot's normal skip-the-confirm behavior, so a machine-authored design change never ships without a human seeing it, no matter how far downstream the pipeline had already gotten.

### Red-gate `TOOL_ERROR` → immediate escalation, never silent retry

The TDD red-gate check (`gates/red_gate.py`) classifies a new test's pre-implementation result as `RED` / `BLOCKING` / `TOOL_ERROR`. A `BLOCKING` result (the test already passes — not discriminating) retries up to a budget. A `TOOL_ERROR` (inconclusive — couldn't tell) **always escalates immediately and never consumes a retry**, because retrying something the harness can't even evaluate would just burn the budget without learning anything. `next_action()` surfaces this as `escalate_skip`, distinct from the ordinary `retry` path.

### Autopilot-watch's fail-closed approval gate

`autopilot-watch` only picks up a ticket when `status: solution` **and** `approved-commit` is set **and** the design files are byte-identical between that SHA and the branch's current HEAD. This isn't an escalation in the sense of asking a question — it's the inverse: the watcher will *never* act on a ticket whose approval might be stale, so a lead who edits a design after approving it doesn't need to remember to revoke anything. Silence is the safe default; the watcher simply won't touch it until a fresh approval lands.

### Autopilot-watch failures and timeouts → needs-attention log + desktop notification

When a dispatched `/autopilot` run fails or times out, the watcher appends to `.harness/autopilot-watch/needs-attention.jsonl` and fires a best-effort OS desktop notification, so a lead running the watcher unattended for hours doesn't have to poll `autopilot-watch status` to find out something needs them. `autopilot-watch status` also reports a running needs-attention count on demand.

---

## What a human sees at an escalation

Every escalation path above converges on the same lead-facing shape: a summary of what was tried, what specifically is still wrong (via the critic's fixed/persisted/new reconciliation or the gate's structured `GateError` list), and a set of concrete next steps — not just "it failed." Resuming from `changes-requested` re-enters `/build`, which the `resolve-pause` audit action records (see below) as the lead's decision to continue.

---

## Reversal and override: undoing after the fact

The escalation triggers above are automatic; these are levers a lead reaches for deliberately, after the fact:

| Command | Effect |
|---|---|
| `/cancel XXXX [--abandon]` | Stop work on a ticket that hasn't shipped: main-free, archives docs, removes the worktree and branch |
| `/abandon XXXX` | Same, framed as "started but dropped" rather than "deliberately cancelled" — a distinct ledger event for reporting purposes |
| `/reopen XXXX` | Bring a terminal ticket (delivered, cancelled, or abandoned) back to `status: solution` on a fresh branch |
| `/rollback XXXX [--dry-run]` | Revert a *delivered* ticket's squash-merge commit via `git revert` (never `git reset`) — twelve fail-closed steps including a dry-run preview and a clean-tree preflight; see [02-commands-and-skills.md](02-commands-and-skills.md) |
| `/replan XXXX` | Throw away and regenerate `solution.md` from scratch, even mid-implementation, with a warning if a worktree already has in-progress work |

None of these require the harness to have escalated first — a lead can reach for any of them at any point the ticket is in a reversible state.

---

## Control levers: config knobs that shift the dial

A lead who wants more or less autonomy for their project as a whole, rather than per-run, has several persistent knobs:

| Knob | Where | Effect |
|---|---|---|
| `MAX_REPAIR_ATTEMPTS` | `.harness/config.py` | How many auto-repair rounds before critic/gate exhaustion escalates to the lead |
| `CRAFT_MAX_ITERATIONS` | `.harness/config.py` | Craft-polish round budget; `0` disables the pass entirely (worktree returned unchanged, no craft commits at all) |
| `CRAFT_REQUIRE_TEST_SURVIVAL` | `.harness/config.py` | Whether the craft pass must additionally survive the pinned pre-polish test set, not just the gate re-run |
| `[policy]` block | `_standards.md`'s `[gates]` fence | Per-gate `required` / `on_block` (`"fail"` / `"pause_for_human"`) — lets a lead mark specific gates as advisory, or as needing a human rather than an auto-block |
| `--no-stack-check` | `/problem` invocation | Skips the tech-stack advisor sub-flow entirely for a new-app ticket, rather than presenting the proposal for approval |
| `autopilot-watch --interval N` | `autopilot-watch start` | How often the watcher polls for newly-approved tickets — a throughput/responsiveness tradeoff, not a safety one |

There's no knob that widens what counts as an escalation trigger — those are fixed, mechanical checks. The knobs only adjust *when* a given trigger fires (repair budget, craft budget) or *whether a matched condition blocks vs. pauses* (policy). A lead who wants stricter human oversight sets tighter budgets or more `pause_for_human` entries; a lead who wants a faster unattended pipeline loosens them — but a genuine BLOCKER, a `TOOL_ERROR`, or an unverified approval always stops the run.

---

## Accountability regardless of autonomy level

`audit.py` appends one identity-stamped JSON line to `.harness/audit.log` for every lead-confirmed decision — `deliver`, `rollback`, `resolve-pause`, `confirm-scope-drift`, `cancel`/`abandon`/`reopen` — naming who made the call (`git config user.name` → `$USER` → `getpass.getuser()`, fail-open so a logging hiccup never blocks the real operation). This is deliberately independent of how autonomous the run was: whether a ticket went through five manual phase-by-phase reviews or a single `/autopilot` call that only paused once, the moments an actual human said "yes" are the same moments recorded here. `ticket-status.md XXXX` surfaces a ticket's own audit entries as a trailing section, so "who approved this and when" is always answerable from the ticket itself, not from institutional memory.

---

## Choosing a level

- **Reviewing every phase individually** — use when the ticket is unusually risky, the requirements are genuinely fuzzy, or you're mentoring someone on how the pipeline works.
- **`/problem` then `/build`, manually** — the default for most feature work. Two checkpoints, full visibility on the diff, nothing else demands attention in between.
- **`/autopilot XXXX`** — once you trust a well-scoped, already-approved ticket to build itself; you still gate the one decision that matters (the design) up front.
- **`autopilot-watch`** — when you're approving several tickets over the course of a day and don't want to remember to come back and type `/autopilot` for each one; the fail-closed approval check is what makes this safe to leave running.
- **Batch autopilot** — when a set of tickets are tightly related and you want them to land as one atomic unit rather than trickle in independently.

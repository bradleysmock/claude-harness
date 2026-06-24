# Multi-Developer Ticketing — Design

**Date**: 2026-06-23
**Status**: Approved (brainstorm) — pending implementation plan
**Topic**: Make the harness ticketing system safe for multiple developers and eliminate orphaned (uncommitted) ticket updates.

## Problem

The current `.tickets/` system works well for one engineer on one machine driving multiple agents, but has two structural weaknesses:

1. **Orphaned updates.** Every status transition relies on the *agent remembering* to run a scoped `git add` + commit to `main`. Nothing enforces it, so `status.md` edits get stranded in the working tree.
2. **Single-machine assumptions.** The `NEXT_TICKET` counter + pid-based `.ticket.lock` only coordinate within one machine. Two developers branching off the same `main` both read the same next number; `NEXT_TICKET` merge-conflicts on every concurrent ticket creation; `.active` assumes one session; and committing every transition straight to `main` serializes metadata writes and races across developers.

## Goals

- Two+ developers (on different machines, sharing one `origin`) can create and drive tickets concurrently without ID collisions or metadata races.
- Orphaned/uncommitted ticket updates become structurally impossible.
- `main` carries a coarse, durable signal of each ticket: **started** and **abandoned**.
- Preserve the system's core value: git-native, self-contained, offline-capable, no external service.
- Leave a clean seam for GitHub Issues to feed in bug-report tickets **later**, with no external dependency built now.

## Non-Goals

- No external issue tracker or coordination server in this iteration (GitHub Issues is a future seam only).
- No automatic abandonment of tickets (too dangerous — explicit only).
- No change to the gate/repair, critic, or panel machinery.

## Approach (chosen)

Stay **git-native**. A shared `origin` is the coordination point. Three mechanisms:

1. **Reserve-on-main claim** for collision-free IDs that doubles as the "started" signal.
2. **State split** — coarse lifecycle on `main`, fine implementation churn on the branch.
3. **Hook-enforced commits** — a Stop-hook guard plus an atomic `ticket` helper make orphaned updates impossible.

Rejected alternatives: an external tracker as source of truth (adds hard network/auth dependency and cache drift); a minimal patch that only fixes the orphan hook (doesn't deliver the start/abandon signal or solve cross-machine claims).

## Design

### 1. Claim protocol — reserve-on-main

Claiming a ticket number is a tiny, immediately-pushed commit to `main`:

1. `git fetch origin main`; acquire local `.ticket.lock` (pid:epoch — retained to serialize same-machine agents and avoid wasted round-trips).
2. Compute `XXXX = max(existing ticket dirs) + 1`. `NEXT_TICKET` is demoted to a non-authoritative cache/hint; the authoritative next number is derived from the existing ticket directories, removing the counter file as the sole conflict point.
3. Write a **stub only**: `status.md` (`status: claimed`, `owner:`, `slug`, `date`) plus a `NEXT_TICKET` bump. No design docs yet.
4. Commit `chore(ticket): XXXX claim` → `git push origin main`.
5. **On push rejection** (another dev claimed `XXXX` first): `git pull --rebase`, recompute `XXXX` (now higher), `git mv` the stub dir to the new number, re-commit, re-push. Retry ≤ 5×; if still conflicting, stop and report to the lead.
6. Release the lock.

Because the claim commit is a lightweight stub, renumber-on-conflict is a cheap `git mv` + re-commit — no design work is lost. **The claim commit is the durable "number taken / work started" signal** other developers see on `main`.

### 2. State split + lifecycle

Per the coarse-on-main / fine-on-branch decision:

| Status | Home | Meaning |
|---|---|---|
| `claimed` | main | number reserved, design starting |
| `solution` | main | design complete, ready to build |
| `implementing` | main | **started** — `/build` created the worktree |
| `review-ready`, `changes-requested` | branch only | build / critic churn |
| `done` / `cancelled` | main | terminal; archived to `completed/` |
| `abandoned` | main | **new** — started but dropped |

`status.md` exists in both homes, but **only the owner mutates a given ticket's status, on its own branch, after the start signal**. Because no one else writes that ticket's status on `main`, the branch→main merge at `/deliver` fast-forwards `status.md` with no conflict.

`status.md` gains an `owner:` field (from `git config user.email`).

**Abandoned** is set **explicitly only** (never automatic). `/status` *flags* stale `implementing` tickets — by `owner` + branch age — as abandonment candidates for a human to decide.

### 3. Orphan cure — guard hook + atomic helper

Two layers, mirroring the existing `stop_full_gate` philosophy (enforce with hooks, don't trust memory):

- **Stop-hook guard.** At turn end, if any *tracked* file under `.tickets/` is modified-but-uncommitted, **block the turn** with a message instructing the agent to commit ticket metadata. This makes orphaned updates structurally impossible. (Skills already commit-before-return per the harness reference; the guard enforces that existing contract.)
- **Atomic `ticket` helper**, shipped in the plugin (not the user repo, to stay dependency-free). `ticket set-status XXXX <status>` edits `status.md` **and** commits in one scoped step (`git add .tickets/XXXX-<slug>/` only). Skills call this instead of hand-editing + remembering to commit, so the easy path is also the correct path; the guard catches anything that bypasses it.

### 4. GitHub seam (reserved, not built)

To allow bug reports to enter via GitHub later with no rework:

- `status.md` gains optional `source:` (default `local`) and `external_id:` fields.
- **All** ID assignment flows through the `ticket` helper, so a future `ticket import-github <issue>` slots in behind that boundary.
- Nothing network-touching ships in this iteration.

### 5. Command & hook deltas

| Surface | Change |
|---|---|
| `/problem` | Claim + push at Phase 1 (early start signal + reservation with retry/renumber); design commit + push at end; records `owner`. |
| `/build` | Commits `implementing` to `main` (the start signal) when creating the worktree; all later status churn stays on the branch. |
| `/deliver` | Merge branch→main (final status rides along), archive to `completed/`, push. |
| `/cancel` | Terminal `cancelled`. New `/abandon` (or `/cancel --abandon`) → `abandoned`. |
| `/status` | Shows `owner`; flags stale `implementing` tickets as abandonment candidates. |
| Stop hook | New orphan guard (block turn on uncommitted tracked `.tickets/` files). |
| `.ticket.lock` | Retained for same-machine agent serialization. |
| `harness-reference.md` | Update Tickets, status-transition table, and "Committing ticket metadata" sections to match. |

## Risks & Mitigations

- **Claim race storms** (many devs creating tickets at once) → bounded retry (≤5) with renumber; lead is notified on exhaustion. Claim commits are tiny, so the window is small.
- **Guard false-positives** blocking legitimate in-progress turns → guard only fires on *tracked* `.tickets/` files at a Stop event; skills always commit-before-return, so this enforces the existing contract rather than adding new burden.
- **Two homes for `status.md`** could confuse merges → invariant that only the owner advances a ticket's status on its branch keeps the merge a fast-forward; documented explicitly.
- **Forgotten push after claim** would reintroduce collisions → claim step pushes as part of the atomic claim; failure to push aborts the claim.

## Success Criteria

- Two developers can each run the create→build→deliver flow concurrently against a shared `origin` with no ID collision and no manual `NEXT_TICKET` conflict resolution.
- After any turn that touches `.tickets/`, there are zero uncommitted tracked ticket files (guard-enforced).
- `main` shows `claimed`/`implementing`/`abandoned`/terminal status for every ticket; implementation-phase sub-states do not appear on `main` until merge.
- `status.md` carries `owner`; `/status` lists owners and stale-ticket candidates.
- `source:`/`external_id:` fields exist and default to `local`; no GitHub code path is invoked.

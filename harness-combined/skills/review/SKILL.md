---
name: review
description: Interactive panel-aware review of a ticket's implementation against its problem / requirements / solution baseline. TRIGGER when the user asks to review a ticket, check a worktree's diff before /deliver, assess whether a ticket is merge-ready, or invoke an interactive post-build review on a specific ticket (e.g. "review ticket 0003", "look at the diff on 0007 before I deliver", "is ticket 0012 ready to merge?"). SKIP for general code review of arbitrary diffs unrelated to a ticket (use the `critique` skill instead — same panel machinery, free-form scope), for ad-hoc style/lint checks (use /gate), and during active /build sessions on the same ticket (wait for /build to finish). Note: /build automatically spawns the critic subagent in code-mode as its final step — this skill is the *interactive* alternative when the lead wants to walk the review conversationally with follow-up questions.
---

# Review skill — interactive panel-aware ticket review

Conduct a code review for a ticket whose `/build` has completed. This skill runs the same panel-aware review process as the critic subagent's `Phase: code` mode (see `${CLAUDE_PLUGIN_ROOT}/context/critic-brief.md`), but **interactively** — the lead sees findings as they're produced and can ask follow-up questions, request deeper dives, or skip ahead to the verdict.

The non-interactive equivalent runs automatically at the end of `/build` as the post-build critic. Invoke this skill when the lead wants to either (a) re-review after fixing earlier BLOCKERs, (b) drive the review conversationally rather than as a one-shot report, or (c) review a ticket whose `/build` happened in a previous session.

## Ticket resolution

If the user named a ticket number, use it. Otherwise scan `.tickets/` for tickets with `status: review-ready`. If exactly one exists, use it; if multiple exist, list them and require the lead to specify before continuing.

## Steps

### Step 0 — Guard against concurrent automated sessions

If `.tickets/.active` exists and contains this ticket's slug, an automated `/build` session may be in progress. Warn the lead and recommend waiting before proceeding. Do not stop — proceed if the lead confirms.

### Step 1 — Read the ticket baseline

Read `problem.md`, `requirements.md`, and `solution.md`. Derive the worktree path from `status.md` (read the `branch` field, strip the `ticket/` prefix, resolve `.worktrees/XXXX-<slug>` relative to project root). Note the path; you'll read it in Step 4.

### Step 2 — Determine active panels

Run `panel_detect.py --root <project_root> <files...>` (files = the worktree's changed/implementation files) against the canonical trigger data in `${CLAUDE_PLUGIN_ROOT}/context/panels/triggers.md`, and parse its JSON output. `active` names the panels to load — Core is always first. For each panel in `candidates`, disposition it (activate or defer) with a one-line reason before reading code. If the response's `skipped` list is non-empty, surface it in the report header. Announce the active panels and any deferred candidates before reading code.

### Step 3 — Load panel definitions

Read only the panel files for active panels. Do not read inactive panels.

### Step 4 — Read worktree + gate findings

Read all implementation and test files in the worktree (`.worktrees/XXXX-<slug>/`).

If `.tickets/XXXX-<slug>/gate-findings.md` exists, read it. **Do not re-flag what the gates already caught** — your value is the panel-level lens gates can't apply.

If `.tickets/XXXX-<slug>/critic-findings.md` exists, read it too — it holds the persisted per-round post-build critic reports and any escalation diagnosis (see "Critic findings file" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). **Cite prior rounds rather than re-deriving them**: reference what earlier rounds already found and what auto-repair changed, and focus your review on what remains open or regressed since the last round.

Read everything before producing any findings.

### Step 5 — Conduct the review

Produce findings across two axes, applied together (not sequentially):

**Axis A — Ticket-baseline checks** (the two ticket-specific dimensions no panel covers; see `critic-brief.md` Step 2.5 for the canonical definitions):

- **Requirements coverage** — Does each functional requirement in `requirements.md` have a corresponding implementation in the worktree AND a passing test that exercises it? Missing implementations or missing tests for stated requirements are **BLOCKER**.
- **Alignment with `solution.md`** — Did the implementation follow the agreed architecture, tech choices, library selections, and overall approach? Significant unjustified deviations are **MAJOR**. Deviations explained in comments / commit messages / added docs are **OBS**.

**Axis B — Panel findings** (the expert-lens hazards from every loaded panel's review dimensions). Apply every relevant dimension. Use the canonical 4-tier vocabulary: **BLOCKER / MAJOR / MINOR / OBS** (see `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`).

### Step 6 — Present findings interactively

Output structured findings inline in the conversation using the same format as `critique`'s output (see `${CLAUDE_PLUGIN_ROOT}/skills/critique/SKILL.md` Output Format) — Verdict at the top, Finding Table, BLOCKER & MAJOR Detail in the compact 2-section format (prose + Fix), MINOR & OBS in tabular form. Apply the same size discipline (≤ 3× source line count) and the same split-bundled-findings rule (rule 11).

Because this is the *interactive* mode (not the subagent one-shot), present in stages:

1. Announce active panels and deferred panels.
2. Output the Verdict and Counts immediately.
3. Stream the Finding Table.
4. Stream the BLOCKER & MAJOR Detail.
5. Stream MINOR & OBS.
6. Offer the lead the chance to ask follow-up questions, request a deeper look at any finding, or proceed to the status transition.

Unlike `critique`, do **not** write the report to `CRITIQUE.md` — the interactive conversation is the deliverable.

### Step 7 — Status transition

**If approved** (no BLOCKER items):
- Keep `status.md` at `review-ready`.
- Tell the lead the ticket is approved and they can run `/deliver XXXX`.

**If changes required** (BLOCKER items exist):
- Update `status.md` to `status: changes-requested`.
- Commit the metadata transition **inside the worktree on the branch** — it must **not** touch `main` (scoped add — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):
  ```
  git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
  git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → changes-requested"
  ```
- List which BLOCKER items need addressing.
- Tell the lead to invoke `/build XXXX` to continue work in the existing worktree.

---

## Differences from the post-build critic subagent

| | Post-build critic (automatic) | This skill (manual) |
|---|---|---|
| Invoked by | `/build` final step | Lead, with `/review XXXX` |
| Conversational | No — one-shot subagent report | Yes — findings stream; lead can ask follow-ups |
| Panels loaded | Yes (via critic-brief Step 1) | Yes (via this skill's Step 2) |
| Ticket-baseline checks | Yes (critic-brief Step 2.5) | Yes (this skill's Step 5 Axis A) |
| Status transition | Yes (handled by `/build` flow) | Yes (handled by this skill's Step 7) |
| Output file | None (returned to parent) | None (inline) |
| Use when | Default post-build gate | Lead wants to drive the review conversationally, or re-review after fixes |

Both produce the same severity findings against the same panel set and the same ticket-baseline checks. The difference is interaction shape.

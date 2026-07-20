# Flow: build --dry-run — ticket mode

Preview a ticket build without touching anything. A dry run runs every gate phase
and the critic in full and prints the plan of files a live build *would* write —
but it writes **no** implementation files, creates **no worktree**, and leaves
`status.md` untouched. It ends by asking whether to proceed with the live build.

Reached from `commands/build.md` when `--dry-run` is present and the surviving
argument selects ticket mode (`validate_dry_run_mode` has already rejected the
spec-mode case). Set `DRY_RUN=true` for this run. The deterministic helpers live
in `dry_run.py`.

Read `.harness/config.py` if it exists for `LANGUAGE`, `PROJECT_ROOT`,
`MAX_REPAIR_ATTEMPTS` (defaults: auto-detect, `.`, 3).

**Announce**: "Dry-run ticket mode for XXXX-slug — no files will be written."

## Step 0 — Reap stale sandboxes

Call `clean_stale_dry_run_tmp(project_root)` (from `dry_run.py`) to remove any
temp dirs left under `.harness/dry-run-tmp/` by a prior interrupted dry run.

## Step 1 — Resolve ticket, generate specs in-memory

Resolve the ticket exactly as `build-ticket.md` Step 1 (scan `.tickets/`, then
`.tickets/completed/`). Confirm `status: solution`. Run the score-spec gate; on
BLOCK, show the failing checks and stop.

Generate specs from `solution.md` following `write-spec-ticket.md` Steps 1–5 **with
`dry_run=True`** — the spec objects are derived in memory but `persist_specs(...,
dry_run=True)` writes nothing to `.harness/specs/` or `.harness/tasks/` (FR-10).
Show the lead the structured spec summaries (id, target_file, description,
acceptance criteria) via `summarize_specs`.

## Step 2 — No worktree, no status transition

A dry run does **not** create the `ticket/XXXX-<slug>` branch or the
`.worktrees/XXXX-<slug>` directory, and does **not** transition `status.md` to
`implementing`. `status.md` stays at `status: solution` throughout (FR-7, FR-8).
Skip `build-ticket.md` Steps 2, 5, and 6 entirely.

## Step 3 — Generate implementations in-memory and gate in a sandbox

For each spec, generate the implementation + tests as usual, but hold them in
memory — do **not** write them to any worktree. Pass the
`(spec, implementation, tests)` triples to `run_dry_run_gates(spec_impls,
project_root, language)`: it writes them into a fresh temp dir under
`.harness/dry-run-tmp/`, runs the full gate suite there, renders the
gate-findings markdown, and **unconditionally removes the temp dir** in a
`finally` (so nothing persists even if a gate raises — FR-6).

Write the returned gate-findings markdown to `.tickets/XXXX-<slug>/gate-findings.md`
(FR-3). This is the one file a dry run writes, and it lives in the ticket
directory, never in a worktree.

## Step 4 — Critic (design phase)

Spawn the critic subagent with **Phase: design**, **Ticket: XXXX-<slug>**,
**Round: 1**, passing the ticket artifacts plus the structured spec metadata
(id, target_file, description, acceptance_criteria) — **not** the raw generated
code. This keeps untrusted generated code out of a tool-capable agent's context.

**Persist the full report.** Write the critic's full structured report to
`.harness/critiques/<YYYY-MM-DD>-<NN>-<slug>.md` at the main project root
(never inside a worktree), using the naming/counter logic from
`skills/critique/SKILL.md`'s Output Format section (date-first filename, a
two-digit same-day counter scanned from existing `.harness/critiques/`
entries, and a kebab-case target slug) rather than re-deriving it. Record the
resulting path as `critic_report_path` — Step 5 passes it to
`render_dry_run_report` so the displayed report shows only a trimmed
header + verdict + finding table plus a pointer to this file.

**No auto-repair.** Per `build-ticket.md` Step 7a, `should_auto_repair(dry_run)`
returns `False` here — the repair loop is suppressed. The critic runs; nothing is
repaired or committed.

## Step 5 — Assemble and render the report

Call `assemble_dry_run_report(ticket_id, specs, gate_findings, critic_findings)`
then `render_dry_run_report(report, critic_report_path)` (the path written in
Step 4) and display the result. The rendered output opens with the header
`=== DRY RUN — no files written ===`, lists the planned specs, the
`would write: <file>` plan (one line per spec — FR-5), the gate findings under
`Gate coverage: indicative only …`, and the critic findings under
`Critic coverage: design-phase panels only …` — trimmed to header + verdict +
BLOCKER/MAJOR/MINOR/OBS finding-count table plus a `Full report:
<critic_report_path>` pointer, never the full critic detail — and ends with the
proceed prompt (FR-9, FR-11). The rendering is deterministic and
timestamp-free (NFR-2).

## Step 6 — Proceed prompt

The rendered report ends by asking whether to run the live build. Stop there —
a dry run never continues to a live build on its own. To proceed, the lead runs
`/build XXXX` (without `--dry-run`).

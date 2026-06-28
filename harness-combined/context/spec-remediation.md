# Spec auto-remediation procedure (Step S)

Autopilot-only. This is the procedure `autopilot-ticket.md`'s **Step S** runs when
the score-spec gate in `build-ticket.md` Step 1 returns **BLOCK**. Interactive
`/build` and `/write-spec` never reach here — their BLOCK is the unchanged hard
stop. The hard stop is the fail-closed default; this procedure overrides it *only*
when reached from autopilot's Step S.

`score-spec.md` is the single source of truth for the check list — this file does
**not** re-enumerate the checks. The fixers and classifier live in
`${CLAUDE_PLUGIN_ROOT}/gates/spec_remediate.py` (pure, unit-tested, no I/O).

## Invariants

- **No worktree yet.** Step S runs *before* any worktree is created. The "fix
  before worktree" invariant holds — a worktree is created only once the verdict
  is PASS/WARN (NFR-1).
- **Authoritative re-score on committed files.** After each pass the revised
  `requirements.md` / `solution.md` are committed to `main`, then `score-spec.md`
  is re-applied to the committed files. The re-score — not the fixer — decides
  whether to continue (FR-7).
- **Structural only.** Mechanical fixers never author prose. The text being
  remediated is the same untrusted artifact text score-spec gates, so the gate
  must not score content written to pass it.
- **Fail closed.** Any BLOCK check the classifier does not recognise routes to the
  hard stop (FR-6). Drift in score-spec's check set bails rather than silently
  passing.
- **Budget.** ≤1 mechanical pass + ≤1 `/refine` pass ⇒ ≤2 re-scores total. Still
  BLOCK after the budget ⇒ hard-stop (FR-8).

## Procedure

Inputs: the score-spec report string from `build-ticket.md` Step 1, and the
ticket's `requirements.md` / `solution.md`.

### S0 — Classify

Call `classify(report)` from `gates/spec_remediate.py`. It buckets each **BLOCK**
check into `mechanical`, `semantic`, or `hard_stop`:

- **`hard_stop` non-empty** (an unrecognised BLOCK check) → **bail now** (go to
  "Hard-stop" below). Do not attempt any fix. This is the forward-compat guard.
- Otherwise proceed with the `mechanical` and `semantic` buckets.

### S1 — Mechanical pass (if `mechanical` non-empty)

Run **one** mechanical pass that fixes *all* mechanical BLOCKs at once:

```
new_req, new_sol, announcements = remediate_mechanical(requirements_text, solution_text)
```

- This applies imperative substitutions (`should`/`may`/`could` → `must`, one FR at
  a time, inline-code spans untouched — FR-4) and structural Test Plan edits
  (append an FR-keyed row whose scenario cell cross-references the FR's existing
  text; remove phantom rows — FR-3).
- **Announce every edit.** Print each line in `announcements` verbatim — one line
  per edit, for lead audit (NFR-1).
- Write `new_req` / `new_sol` back to the ticket's `requirements.md` /
  `solution.md`.
- **Commit to `main`** (scoped add — see "Committing ticket metadata" in
  `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):
  ```
  git add .tickets/XXXX-<slug>/
  git commit -m "chore(ticket): XXXX spec-remediate (mechanical)"
  ```
- **Re-score** the committed files per `score-spec.md`. This is re-score #1.
  - **PASS/WARN** and no `semantic` checks were ever flagged → the ticket was
    cleared by mechanical fixes only. It stays **fully autonomous** (FR-9): return
    `succeeded(autonomous=True)` to Step S.
  - **PASS/WARN** but `semantic` checks remain in the new report → continue to S2.
  - **Still BLOCK** → re-classify the new report; if the only remaining BLOCKs are
    `semantic`, continue to S2; otherwise (mechanical still BLOCK, or a new
    `hard_stop`) **hard-stop** (the budget allows no second mechanical pass).

If `mechanical` was empty, skip S1 and go straight to S2.

### S2 — Refine pass (if `semantic` BLOCKs remain)

Semantic checks (`FR count`, `No placeholders`) need judgement. Run **one**
non-interactive `/refine` pass (see `${CLAUDE_PLUGIN_ROOT}/commands/refine.md`,
"Autopilot (non-interactive) mode"):

- Single pass, fixing **only** the flagged checks, deriving content **only** from
  existing artifact text, surfacing no Open Questions / next-command prompts.
- If `/refine` reports it cannot drive the fix from existing text (e.g. an
  `FR count` BLOCK with no derivable FR), it **bails** — it must not fabricate
  net-new scope. Treat that as **hard-stop**.
- `/refine` commits the revised artifact to `main` itself.
- **Re-score** the committed files. This is re-score #2 (budget exhausted).
  - **PASS/WARN** → return `succeeded(autonomous=False)` to Step S. A refine clear
    reached build but **must not auto-deliver** — Step B confirms the diff (FR-9).
  - **Still BLOCK** → **hard-stop**.

### Hard-stop

Remediation could not clear the BLOCK within budget (or hit a `hard_stop` / an
undrivable refine). Return `bail` to Step S with the residual score-spec report.
No worktree was created. Step S surfaces the residual checks to the lead and stops
— exactly the behavior interactive `/build` would have had on the original BLOCK.

## Outcomes returned to Step S

| Outcome                       | Meaning                                              | Step S next         |
|-------------------------------|------------------------------------------------------|---------------------|
| `succeeded(autonomous=True)`  | Cleared by mechanical fixes only.                    | Resume build; Step B auto-delivers. |
| `succeeded(autonomous=False)` | A `/refine` pass was needed to clear it.             | Resume build; Step B **confirms** (no silent merge). |
| `bail`                        | Budget exhausted, unrecognised check, or undrivable. | Hard-stop to the lead. |

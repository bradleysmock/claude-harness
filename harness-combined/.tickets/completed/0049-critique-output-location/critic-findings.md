# Critic findings — 0049-critique-output-location

## Round 1 — 2026-07-07

**Phase:** code · **Verdict:** REVISE · 0 BLOCKER · 3 MAJOR · 1 MINOR · 2 OBS
**Active panels:** Core + Testing (Python deferred — the one `.py` file is a pure content-grep test).

| ID | Severity | Location | Finding |
|----|----------|----------|---------|
| C-01 | MAJOR | `skills/status/SKILL.md` | "Reverse lexical sort" keyed on the leading `<target-slug>`, not the date → "three most recent" not ordered by recency across targets. |
| C-02 | MAJOR | `skills/critique/SKILL.md` | `--comment` re-derived `.harness/critiques/` relative to cwd, contradicting the main-root/never-in-worktree write rule. |
| C-03 | MAJOR | `tests/test_0049_critique_output_docs.py` | FR-2's promised ignore-coverage assertion missing; test only checked `critiques/` was *listed* in the structure block. |
| C-04 | MINOR | `commands/init.md` | Structure-block comment claimed "git-ignored" but Step 4 never added `.harness/` to `.gitignore`. |
| C-05 | OBS | `skills/critique/SKILL.md` | Pointer in `critic-findings.md` references a git-ignored (machine-local) report path — deliberate one-durable-copy tradeoff, logged. |
| C-06 | OBS | worktree root `REVIEW-FINDINGS-2026-07-05.md` | Pre-existing stray review file tracked on main — out of scope for 0049. |

**Auto-repair (round 1):**
- **C-01** — reordered the report filename scheme to `<YYYY-MM-DD>-<NN>-<target-slug>.md` (date leads) in `skills/critique/SKILL.md`; a plain reverse-lexical sort is now globally newest-first. Updated `skills/status/SKILL.md` Step 4 sort explanation + example to match.
- **C-02** — `--comment` block now reuses the exact main-root-anchored absolute `<report-path>` resolved+written above instead of re-deriving it relative to cwd; prose warns against cwd re-derivation.
- **C-03 / C-04** — `commands/init.md` Step 4 now adds `.harness/` to `.gitignore` (wholesale — covers `results/`, `critiques/`, `checkpoints/`, `memory.db`); the structure-block comment is now accurate. Added `test_init_gitignores_harness_state` as the real ignore-coverage assertion.
- **C-05 / C-06** — OBS, logged; no change (C-06 is pre-existing out-of-scope debt).

## Round 2 — 2026-07-07

**Phase:** code · **Verdict:** APPROVE · 0 BLOCKER · 0 MAJOR · 1 MINOR · 2 OBS

All three Round 1 MAJORs verified **RESOLVED** (C-01 date-leading filename + matching status sort; C-02 `<report-path>` reuse with cwd-re-derivation warning; C-03 real ignore-coverage test + init.md `.harness/` gitignore entry). No regressions in the four in-scope files.

New findings:
- **C-07 (MINOR)** — `README.md` still advertised `/critique` writing `CRITIQUE.md`, contradicting the shipped `.harness/critiques/` behavior. **Repaired** (out of declared scope but a direct misdescription of this ticket's feature): updated the Skills-table row and command reference to point at `.harness/critiques/`, and added `test_readme_describes_critiques_directory_not_cwd_file` to lock it.
- **C-08 (OBS)** — `report_path = Path(report_path)` in the illustrative `--comment` snippet is harmless pseudocode; no change.
- **C-09 (OBS)** — same pre-existing stray `REVIEW-FINDINGS-2026-07-05.md`; out of scope.

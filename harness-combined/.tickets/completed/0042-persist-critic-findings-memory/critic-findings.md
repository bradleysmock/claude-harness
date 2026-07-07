# Critic findings — 0042-persist-critic-findings-memory

## Round 1 — 2026-07-06

**Active panels:** Core (always active). AI/prompt-doc-consistency and Python-test lenses considered; neither surfaced findings beyond Core + Step 2.5.

### BLOCKER

**BLOCKER-1 — FR-4 is wired by filename but cannot extract critic patterns; the helper's format contract rejects `critic-findings.md`.**
Files: `context/flows/deliver-ticket.md:346-362`; `context/helpers/parse-gate-findings.md:28-33, 36-57`.
Deliver Step 5 routes `critic-findings.md` through `parse-gate-findings.md`, but that helper's Step 1 short-circuits to an empty list unless the file contains a `## <gate-name>` section with a `**Status**: FAIL` line, and Step 2 extracts only from such sections. `critic-findings.md` has `## Round N — <date>` / `## Escalation diagnosis — <date>` sections with `**BLOCKER**`/`**MAJOR**` prose bullets — no `**Status**: FAIL`. Executed faithfully, the helper returns `[]` for every `critic-findings.md`, so no critic pattern reaches candidates. FR-4 is nominally wired but functionally inert; the acceptance criterion "deliver Step 5 output cites a pattern found only in critic-findings.md" is unachievable. Fix: give the helper an explicit critic-report parse path (walk `**BLOCKER**`/`**MAJOR**` bullets, tag `gate="critic"`) and add a covering test.

### MAJOR

**MAJOR-1 — Critic verification rounds run inside `repair-escalation.md` are never appended to `critic-findings.md`.**
Files: `context/flows/repair-escalation.md:66, 89` vs the pattern at `build-ticket.md:220-233, 254`.
Phase 1 and Phase 2 each re-spawn the critic and only "Display its report verbatim" — neither appends that round to `critic-findings.md`. FR-1 / problem.md say every critic round's report is appended. Fix: after each re-spawn in Phase 1 and Phase 2, add the same append+commit instruction Step 7a carries, plus a docs-grep.

### MINOR

**MINOR-1 — Merged critic records carry no meaningful `gate` field; dedup "across both files" under-specified.** (`deliver-ticket.md:353-355`.) Critic-origin candidates need a defined `gate` value — use `critic`, consistent with the memory records. Contingent on BLOCKER-1.

### OBS

**OBS-1 — Docs-grep tests verify string presence, not flow behavior; BLOCKER-1 and MAJOR-1 both pass the current suite green.** A behavioral test running a sample `critic-findings.md` through Step 5 extraction would have caught BLOCKER-1.
**OBS-2 — FR-3 test asserts gate partitioning, which `memory.py` genuinely enforces (`WHERE gate = ?`).** NFR-2 (no schema change) holds. No action.

### Step 2.5 — Requirements coverage & solution alignment

- FR-1: covered for `build-ticket.md` Step 7 / Step 7a; **incomplete** for escalation-flow rounds (MAJOR-1).
- FR-2: fully covered (`repair-escalation.md`).
- FR-3: covered (`build-ticket.md` Step 4e + memory round-trip).
- FR-4: filename wired, **extraction non-functional** (BLOCKER-1).
- FR-5: covered (review + debug skills).
- NFR-1 / NFR-2: satisfied.
- Solution alignment: the `parse-gate-findings.md` routing decision (undocumented) is where FR-4 breaks.

## Round 2 — 2026-07-07

Re-verification after auto-repair round 1.

**Round 1 disposition:** BLOCKER-1 (FR-4 inert) — **CLEARED** (Step 2c critic parser + Step 5 `source_kind="critic"` wiring; MINOR-1 folded in, records tagged `gate="critic"`). MAJOR-1 (escalation rounds not persisted) — **CLEARED** in both Phase 1 and Phase 2.

### BLOCKER
None.

### MAJOR
None. Repair introduced no new BLOCKER/MAJOR. Dedup key `(gate, pattern)` matches the render template; `commit -am` for `critic-findings.md` is safe (file already tracked by that point).

### MINOR
**MINOR-1 — Helper preamble/return prose still says it reads "only the local `gate-findings.md`".** `parse-gate-findings.md:3,155,157` contradict the dual-source reality after generalization. Generalize the wording to cover `findings_path`/critic input.
**MINOR-2 — Extracted critic `pattern` carries redundant `**SEVERITY-n — ` label + `**` markers.** Strip the leading severity-label prefix and trailing `**` before the 120-char cap.

### OBS
**OBS-1 — Step 2c "escalation sections follow the same convention" is imprecise** (they carry no BLOCKER/MAJOR bullets; diagnosis lands in memory.db via FR-2). No action.
**OBS-2 — Verification remains docs-grep only; no fixture drives a sample critic-findings.md through Step 2c.** Acceptable within the ticket's docs-grep strategy.

### Step 2.5
FR-1..FR-5 covered; FR-4 now functional. NFR-1/NFR-2 satisfied. Solution alignment restored (dual-source routing now documented). **Net: both Round 1 findings cleared; no gating findings remain.**

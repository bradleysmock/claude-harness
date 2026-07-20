# Solution

**Ticket**: 0066
**Title**: Autopilot mode flag: build-ticket.md branches explicitly; shrink autopilot-ticket.md to mode plus steps S/A/B

## Approach

Replace `autopilot-ticket.md`'s narrative "watch for this condition inside
build-ticket.md" prose with an explicit mode signal that `build-ticket.md` itself
checks at each of its three lead-facing decision points. `autopilot-ticket.md`
sets `MODE=autopilot` once, before delegating, then only defines what happens
next (Steps S/A/B). The branch condition is a real, unit-tested Python predicate
— `should_auto_repair(dry_run)` in `dry_run.py` is the actual precedent, not
prose — so this ticket matches its shape, not just its appearance.

## Components

| Component | Responsibility |
|---|---|
| `mode_branch.py` (new) | `is_autopilot_mode(mode: str) -> bool` — pure predicate, `mode == "autopilot"`. Unit-tested for `"autopilot"` → `True`, `""`/`"interactive"`/anything else → `False`. |
| `context/flows/autopilot-ticket.md` | Announce autopilot mode, set `MODE=autopilot`, delegate to `build-ticket.md`, define Steps S/A/B only. |
| `context/flows/build-ticket.md` Step 1 | On score-spec BLOCK: evaluate `is_autopilot_mode(MODE)` → True continues at Step S; False keeps today's stop-and-report, preserved verbatim. |
| `context/flows/build-ticket.md` Step 7d | On repair exhaustion: evaluate `is_autopilot_mode(MODE)` → True continues at Step A; False keeps today's `changes-requested` + ask-the-lead, preserved verbatim. |
| `context/flows/build-ticket.md` Steps 7b/7c | On clean/repaired build: evaluate `is_autopilot_mode(MODE)` → True continues at Step B; False keeps today's "tell the lead, list options", preserved verbatim. |
| `tests/test_mode_branch.py` (new) | Unit tests for `is_autopilot_mode`. |
| `tests/test_0066_autopilot_mode_flag.py` (new) | Content-verification pins for the three explicit branches and the shrunk `autopilot-ticket.md`, plus preserved-wording assertions. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| A real pure predicate `is_autopilot_mode()` in a new module, called by name at all three sites — not a prose-only `if MODE == "autopilot"` | Critic round 1 (BLOCKER): `should_auto_repair(dry_run)` is an actual unit-tested function, not narrative; prose-only checks would just relocate the original defect (model-interpreted cue) rather than close it, and violate CLAUDE.md's LLM/Python boundary test. |
| One shared predicate for all three sites, not three separate resolver functions | The three sites differ only in their post-True continuation (Step S/A/B), which stays in flow prose; the boolean condition is identical, so one tested predicate covers all three call sites. |
| Single flag value `autopilot` (vs. unset/interactive), batch mode untouched | Batch mode already has its own dedicated override block; scope stays to ticket-mode interception removal. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-6 | Unit | `is_autopilot_mode("autopilot")` → `True`; `""`/`"interactive"` → `False` (unset `MODE` normalizes to `""`, never `None`, at every call site). |
| FR-2 | Content-verification | Step 1 calls `is_autopilot_mode(MODE)`, names Step S; stop-and-report text preserved verbatim. |
| FR-3 | Content-verification | Step 7d calls `is_autopilot_mode(MODE)`, names Step A; `changes-requested`/ask-lead text preserved verbatim. |
| FR-4 | Content-verification | Steps 7b/7c call `is_autopilot_mode(MODE)`, name Step B; "tell the lead" text preserved verbatim. |
| FR-1, FR-5 | Content-verification | `autopilot-ticket.md` sets `MODE=autopilot`, omits removed interception headings, keeps Steps S/A/B. |
| FR-7, NFR-1 | Regression | `autopilot-batch.md` unchanged; `test_autopilot_batch_docs.py`, `test_0014_build_flow.py`, `test_spec_remediation_flow.py` pass unmodified. |

## Tradeoffs

- **Chose one shared predicate over per-site resolvers because**: the three sites
  share an identical boolean condition; splitting it three ways would test the
  same logic three times for no behavioral difference.
- **Accepting risk of**: the post-True continuation (which Step to jump to) still
  lives in prose, not Python — only the yes/no gate is machine-verified. Full
  machine-dispatch of *destinations* is out of scope; these are flow docs the
  model executes, not a runtime with a dispatcher to call into.

## Risks

- Editing `build-ticket.md`'s three stop points risks drifting the interactive
  wording. Mitigation: preserved-wording test rows above assert the pre-existing
  text verbatim, not just "existing suite still passes."
- Removing interception prose from `autopilot-ticket.md` could drop a load-bearing
  nuance (e.g. "claim-time worktree already exists" framing). Mitigation: fold
  such framing into the corresponding `build-ticket.md` branch text.
- The "readable standalone" acceptance criterion (no cross-reference needed) is a
  comprehension property, not string-matchable — verified by manual read-through
  at the diff-review checkpoint, not an automated test.

## Implementation Order

1. Write `tests/test_mode_branch.py` (red — `is_autopilot_mode` doesn't exist yet)
   and `tests/test_0066_autopilot_mode_flag.py` (red — asserts text not yet in
   the docs), per CLAUDE.md's tests-before-implementation rule.
2. Implement `mode_branch.py`; confirm `test_mode_branch.py` goes green.
3. Edit `build-ticket.md` Step 1, then Step 7d, then Steps 7b/7c — each preserving
   the interactive-path wording verbatim alongside the new branch.
4. Update `autopilot-ticket.md`: set `MODE=autopilot`, remove the interception
   section, keep delegation plus Steps S/A/B.
5. Run the full flow-doc test suite; confirm `test_0066_autopilot_mode_flag.py`
   and all pre-existing tests are green.

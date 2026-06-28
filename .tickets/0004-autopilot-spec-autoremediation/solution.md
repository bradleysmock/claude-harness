# Solution

**Ticket**: 0004
**Title**: Autopilot auto-remediates score-spec BLOCKs instead of bailing

## Approach

Add a **score-spec BLOCK interception** to `autopilot-ticket.md`, mirroring its
existing Divergence/Clean-build pattern. On BLOCK from `build-ticket.md` Step 1,
autopilot diverges to a bounded Step S: classify, apply structural mechanical
fixes and/or one autonomous `/refine` pass, commit, re-score the committed files,
then resume or bail. `build-ticket.md`'s hard stop is unchanged and is the
fail-closed default — only Step S overrides it, so any context lacking that
override hard-stops.

## Components

- **`autopilot-ticket.md`** — add Step S + interception note; Step B confirm carve-out (Step A unchanged).
- **`build-ticket.md` Steps 1–2** — no behavior change; one line: hard stop is the default, overridden *only* by Step S.
- **`refine.md`** — add a non-interactive autopilot mode: single pass, fix only flagged checks, derive from existing text only, no prompts, bail if undrivable.
- **`gates/spec_remediate.py`** (new, testable) — pure functions for the two mechanical fixes (append-row-for-FR, substitute-token); no generative authoring.
- **`context/spec-remediation.md`** (new) — Step S procedure; score-spec.md is the single source of the check list (no re-enumeration).

## Trust boundary & fail-closed

The text being remediated is the same untrusted input score-spec gates, so the
gate must not score content authored to pass it:
- Mechanical fixes are **structural only** — FR-keyed row (cell = cross-ref to the
  FR's text) or literal `should/may/could`→`must`. No prose synthesis. The
  authoritative re-score runs on the committed artifact.
- A BLOCK reason absent from the classification **falls through to bail**.
- Mechanical-only clear stays autonomous; a semantic `/refine` clear reaches build
  but is **not** auto-delivered — Step B confirms the diff (no silent merge).

## Classification

| score-spec check    | Severity | Handling                          |
|---------------------|----------|-----------------------------------|
| Test-plan coverage  | BLOCK    | mechanical (structural row edit)  |
| Imperative language | BLOCK    | mechanical (token substitution)   |
| FR count (< 3)      | BLOCK    | semantic → /refine (non-interactive; bail if undrivable) |
| No placeholders     | BLOCK    | semantic → /refine (non-interactive) |
| any other BLOCK     | —        | fall through → hard-stop/bail (forward-compat guard) |

**Budget**: one mechanical pass (fixes *all* mechanical BLOCKs at once) → re-score
→ one single-pass `/refine` (interactive steps suppressed) → re-score. ≤2
re-scores, ≤1 refine pass. Still BLOCK → bail.

## Test Plan

| Requirement | Test Type   | Scenario(s)                                          |
|-------------|-------------|------------------------------------------------------|
| FR-1        | Integration | BLOCK ticket enters Step S, not lead hand-off.       |
| FR-2        | Unit        | Classifier labels each failing check correctly.      |
| FR-3        | Unit        | Missing row appended structurally (FR-keyed, cross-ref cell); phantom row removed; re-score PASS. |
| FR-4        | Unit        | Only the flagged token changes; rest of FR untouched; re-score PASS. |
| FR-5        | Integration | Placeholder/FR-count BLOCK routes to `/refine` non-interactive mode. |
| FR-6        | Unit        | Synthetic BLOCK check absent from table → fall-through to bail (fabricated name). |
| FR-7        | Integration | Re-score runs on committed files after each pass.    |
| FR-8        | Integration | Fix clears A, re-score BLOCKs on B → bails; assert ≤2 re-scores performed. |
| FR-9        | Integration | Mechanical-only → autonomous; refine path → Step B confirm, no silent merge. |
| FR-5/9      | Integration | FR-count refine that can't derive an FR bails, does not fabricate. |
| NFR-1       | Unit        | Each mechanical fix emits its one-line audit announcement.   |
| FR-10       | Integration | Interactive `/build` on same BLOCK ticket still hard-stops. |

## Tradeoffs & Risks

- **Refine-path tickets lose auto-deliver**: accepted; unapproved scope must not
  merge unseen. Wrong refine scope is gated by Step B + audit trail.
- **Autopilot-only via default-deny**: no new flag; absent Step S the hard stop
  holds. Classification drift fails closed (unclassified BLOCK → bail).

## Implementation Order

1. Build `gates/spec_remediate.py` pure fixers + unit tests (FR-2,3,4,6).
2. Write `context/spec-remediation.md` (Step S procedure, references score-spec.md).
3. Add the non-interactive autopilot mode to `refine.md`.
4. Add Step S + interception + Step B carve-out to `autopilot-ticket.md`; add the
   default-stop clarifying line to `build-ticket.md` Steps 1–2.
5. Add integration fixtures: known-BLOCK tickets exercising remediate/bail/confirm.

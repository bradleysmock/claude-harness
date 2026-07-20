# Solution

**Ticket**: 0058
**Title**: Single-source severity tiers: define BLOCKER/MAJOR/MINOR/OBS in harness-reference only

## Approach

Keep the harness-reference block as the single canonical definition, rewording all
four tier lines phase-neutrally. Replace the two drifted copies (critic-brief.md,
critique/SKILL.md) with heading-named pointers that tell the reader to load that
section. Add a drift test whose block-signature matcher fails on re-duplication in
runtime-loaded prose, whose scan is fail-closed (root/floor/heading sanity), and
whose parser-pin keeps prose and `critic_finding_parser._SEVERITIES` in sync.

## Components

| Component | Responsibility |
|-----------|----------------|
| `context/harness-reference.md` edit | Canonical block under a stable "Severity tiers" heading: BLOCKER -> "blocks the next checkpoint (design approval or merge)" (no `/deliver` tail); MAJOR "new ticket" clause audited; MINOR/OBS logging wording made phase-neutral (no "deliver summary") |
| `context/critic-brief.md` edit | Step 4 keeps one vocabulary sentence + pointer naming the exact heading, with "read that section before producing findings"; four bullets removed |
| `skills/critique/SKILL.md` edit | Severity guide bullets replaced by the same heading-named pointer form |
| `tests/test_0058_severity_single_source.py` | Matcher `find_tier_blocks(text)`; fail-closed tree scan; canonical-block, pointer-heading, and parser-pin assertions; synthetic hit/miss/near-miss fixtures |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Tier-line regex: `**TIER**` at bullet/table-cell start, bold closing at the tier name, then em dash / colon / hyphen / pipe; block = 4 tiers in a 6-line window | Catches both live formats and table re-definitions; bold-close rule excludes build-ticket's "**BLOCKER and MAJOR findings...**" policy bullets; FR-8 negatives prove usage lines never false-positive |
| Fail-closed scan | Each scan root must exist and contribute >= 1 md file; harness-reference must appear in the scanned set; the pointer-named heading must exist — any miss is a loud failure, not a vacuous pass (0043 principle) |
| Matcher lives in the test module | No production surface needed; avoids a new top-level module name (dep-shadowing risk) |
| Paths anchored to `Path(__file__).parent.parent` | Location-relative, cwd-immune; scans only this plugin's tree |
| Parser pin via `import gates.critic_finding_parser` | Direct equality with `_SEVERITIES`; conftest puts repo root on `sys.path`; the private-name coupling is the intended loud failure on rename |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Integration | Exactly one block in harness-reference; four tiers in order; "checkpoint" present in BLOCKER; no "deliver summary" token in the block |
| FR-2        | Integration | critic-brief names the heading + read instruction; zero tier blocks |
| FR-3        | Integration | critique/SKILL.md has the heading-named pointer; zero tier blocks |
| FR-4        | Unit + Integration | 4-bullet and 4-table-row snippets -> matched; scan of real tree finds no block outside harness-reference; injected copy in a tmp clone -> fails |
| FR-5        | Unit        | Canonical block with a tier removed -> fails; duplicated block in harness-reference itself -> fails |
| FR-6        | Unit        | tmp clone with renamed `context/` root, emptied root, or renamed heading -> each fails loudly |
| FR-7        | Integration | Names parsed from the canonical block == `_SEVERITIES` |
| FR-8        | Unit        | Snippets from cryptography.md, uswds.md, build-ticket.md must-fix bullets (bold past tier name), review/SKILL.md vocabulary line -> not matched |
| NFR-1       | Integration | Suite run under `--import-mode=importlib` |
| NFR-2       | Integration | Gate-exact ruff (`--select E,F,W,I --ignore E501`) + mypy clean on the test file |

## Tradeoffs

- **Chose a 6-line-window signature over exact-block matching because**: it catches
  reworded or reordered copies (the drift actually observed), at the cost of FR-8
  negative fixtures to prove usage lines never false-positive.
- **Accepting risk of**: evasion by free prose or an *unbolded* table
  (`| BLOCKER | ... |`, the parser's finding-table idiom) — judged unlikely for a
  definition block, and the canonical-count assertion still catches in-place edits.

## Risks

- critic-brief.md / critique/SKILL.md are shared hotspots for concurrent tickets.
  Mitigation: edits are small deletions + one-liners; rebase-and-rerun per the
  delivery recipe.
- Critic subagents now depend on reading the harness-reference section; the pointer
  carries an explicit read instruction and FR-6 keeps the heading from rotting.
- Sibling harness projects keep their own copies; scan is deliberately anchored to
  this plugin's tree only.

## Implementation Order

1. Tests first: matcher fixtures + tree-scan/parser-pin/fail-closed assertions
   (red: two duplicate blocks exist).
2. Edit `context/harness-reference.md`: stable heading + all-tier phase-neutral wording.
3. Edit `context/critic-brief.md` and `skills/critique/SKILL.md` to heading-named pointers.
4. Test green; gate-exact ruff/mypy on the test file; targeted pytest run.

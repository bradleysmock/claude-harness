# Requirements

**Ticket**: 0058
**Title**: Single-source severity tiers: define BLOCKER/MAJOR/MINOR/OBS in harness-reference only

## Functional Requirements

1. `context/harness-reference.md` must contain exactly one canonical tier-definition
   block naming all four tiers in order, with **all four** tier lines worded
   phase-neutrally: no deliver-pipeline tokens ("deliver summary"), and BLOCKER
   naming checkpoint-or-merge — usable verbatim by design review, code review, and
   standalone diff critique.
2. `context/critic-brief.md` must drop its inline tier bullets and point to the
   exact severity-tiers heading in harness-reference, instructing the critic to
   read that section before producing findings.
3. `skills/critique/SKILL.md` must replace its Severity guide bullets with the
   same heading-named pointer form.
4. The drift test must scan every `*.md` under `context/`, `commands/`, `skills/`,
   `agents/`, plus `README.md` and `CLAUDE.md`, and fail when a tier-definition
   block appears outside harness-reference. A tier line is `**TIER**` at bullet or
   table-cell start, bold closing at the tier name, followed by an em dash, colon,
   hyphen, or table pipe; a block is all four tiers within a 6-line window. Scope
   is runtime-loaded prose only — `docs/` and `.tickets/` are excluded as
   historical, non-loaded records.
5. The drift test must fail when the canonical block loses a tier or its count in
   harness-reference is not exactly one.
6. The scan must fail closed: a missing scan root (`README.md` and `CLAUDE.md`
   count as single-file roots), a root contributing zero markdown files,
   harness-reference absent from the scanned set, or the pointer-named heading
   missing from harness-reference must each fail loudly — never a vacuous pass.
7. The drift test must assert the four tier names parsed from the canonical block
   equal `gates.critic_finding_parser._SEVERITIES`.
8. The drift test must not flag severity usage: single-line mentions, policy lines,
   panel severity conventions, and bold spans extending past the tier name
   (build-ticket.md "**BLOCKER and MAJOR findings are must-fix.**") must stay green.

## Non-Functional Requirements

1. Test uses stdlib + pytest only and passes under `--import-mode=importlib`.
2. The test file must be clean under the gate's ruff flags and mypy.

## Test Strategy

| Type        | Rationale                                                          |
|-------------|--------------------------------------------------------------------|
| Unit        | Block-signature matcher on synthetic md snippets (hits and misses) |
| Integration | Drift test against the real tree; parser-pin; fail-closed sanity   |

## Acceptance Criteria

- After the edits, the only tier-definition block in scanned prose is
  harness-reference's, with no "deliver summary" token; critic-brief and
  critique/SKILL.md contain heading-named pointers instead.
- The drift test passes on the edited tree and fails when a four-bullet copy is
  reintroduced into any scanned file (verified via tmp fixture).
- Renaming a scan root or the severity-tiers heading in a tmp clone fails the test.
- The parser-pin assertion fails if a tier is renamed in only one of prose or
  `_SEVERITIES`; full targeted pytest run green with the tooled Python.

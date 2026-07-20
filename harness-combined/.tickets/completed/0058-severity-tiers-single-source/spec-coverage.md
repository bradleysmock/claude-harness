# Spec Coverage Map

**Ticket**: 0058-severity-tiers-single-source
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| AC-2 | AC | The drift test passes on the edited tree and fails when a four-bullet copy is | 0058-severity-tiers-single-source-consolidation |
| AC-3 | AC | Renaming a scan root or the severity-tiers heading in a tmp clone fails the test. | 0058-severity-tiers-single-source-consolidation |
| AC-4 | AC | The parser-pin assertion fails if a tier is renamed in only one of prose or | 0058-severity-tiers-single-source-consolidation |
| FR-1 | FR | `context/harness-reference.md` must contain exactly one canonical tier-definition | — |
| FR-2 | FR | `context/critic-brief.md` must drop its inline tier bullets and point to the | — |
| FR-3 | FR | `skills/critique/SKILL.md` must replace its Severity guide bullets with the | — |
| FR-4 | FR | The drift test must scan every `*.md` under `context/`, `commands/`, `skills/`, | — |
| FR-5 | FR | The drift test must fail when the canonical block loses a tier or its count in | — |
| FR-6 | FR | The scan must fail closed: a missing scan root (`README.md` and `CLAUDE.md` | — |
| FR-7 | FR | The drift test must assert the four tier names parsed from the canonical block | — |
| FR-8 | FR | The drift test must not flag severity usage: single-line mentions, policy lines, | — |
| AC-1 | AC | After the edits, the only tier-definition block in scanned prose is | — |

## Uncovered

- FR-1 (FR): `context/harness-reference.md` must contain exactly one canonical tier-definition
- FR-2 (FR): `context/critic-brief.md` must drop its inline tier bullets and point to the
- FR-3 (FR): `skills/critique/SKILL.md` must replace its Severity guide bullets with the
- FR-4 (FR): The drift test must scan every `*.md` under `context/`, `commands/`, `skills/`,
- FR-5 (FR): The drift test must fail when the canonical block loses a tier or its count in
- FR-6 (FR): The scan must fail closed: a missing scan root (`README.md` and `CLAUDE.md`
- FR-7 (FR): The drift test must assert the four tier names parsed from the canonical block
- FR-8 (FR): The drift test must not flag severity usage: single-line mentions, policy lines,
- AC-1 (AC): After the edits, the only tier-definition block in scanned prose is

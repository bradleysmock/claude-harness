# Spec Coverage Map

**Ticket**: 0062-stable-critic-finding-ids
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | The system must expose `finding_key(f) -> (file, line, severity, code)`, | — |
| FR-2 | FR | The system must provide `reconcile(prev, curr) -> ReconciliationResult` | — |
| FR-3 | FR | `reconcile` must take only pre-built `Finding` lists — no parsing or | — |
| FR-4 | FR | Step 7 (round 1) and Step 7a (each repair round) must call `reconcile` | — |
| FR-5 | FR | Every round's findings appended to `critic-findings.md` — round 1 onward | — |
| FR-6 | FR | `reconcile` must filter both `prev` and `curr` to BLOCKER/MAJOR before | — |
| FR-7 | FR | `reconcile` must count key occurrences per round (multiset semantics), so | — |
| AC-1 | AC | Round-1/round-2 lists differing by one fixed + one new BLOCKER reconcile to | — |
| AC-2 | AC | `critic-findings.md` every round's section, starting at round 1, includes | — |
| AC-3 | AC | Existing ticket-0031 dedup tests pass unchanged. | — |

## Uncovered

- FR-1 (FR): The system must expose `finding_key(f) -> (file, line, severity, code)`,
- FR-2 (FR): The system must provide `reconcile(prev, curr) -> ReconciliationResult`
- FR-3 (FR): `reconcile` must take only pre-built `Finding` lists — no parsing or
- FR-4 (FR): Step 7 (round 1) and Step 7a (each repair round) must call `reconcile`
- FR-5 (FR): Every round's findings appended to `critic-findings.md` — round 1 onward
- FR-6 (FR): `reconcile` must filter both `prev` and `curr` to BLOCKER/MAJOR before
- FR-7 (FR): `reconcile` must count key occurrences per round (multiset semantics), so
- AC-1 (AC): Round-1/round-2 lists differing by one fixed + one new BLOCKER reconcile to
- AC-2 (AC): `critic-findings.md` every round's section, starting at round 1, includes
- AC-3 (AC): Existing ticket-0031 dedup tests pass unchanged.

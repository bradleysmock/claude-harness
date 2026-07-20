# Requirements

**Ticket**: 0062
**Title**: Stable critic finding IDs

## Functional Requirements

1. The system must expose `finding_key(f) -> (file, line, severity, code)`,
   shared by `gates/comment_deduplicator.critic_hash` and the new reconciler
   — no duplicated key logic.
2. The system must provide `reconcile(prev, curr) -> ReconciliationResult`
   classifying findings by `finding_key` into `fixed` (in prev, not curr),
   `persisted` (in both — returns curr's Finding, the current prose), and
   `new` (in curr, not prev).
3. `reconcile` must take only pre-built `Finding` lists — no parsing or
   harvesting inside it. Step 7/7a must harvest `prev` from the hidden
   `<!-- harness-finding-key file:line:severity:code -->` marker (mirrors
   `comment_deduplicator.marker_for`) in the prior round's
   `critic-findings.md`, not re-parsed prose (avoids `_HEADER_RE` collisions).
4. Step 7 (round 1) and Step 7a (each repair round) must call `reconcile`
   and announce a one-line summary; the Step 7a call must sit at that step's
   entry, before its skip-to-7c branch (mirrors the dry-run-suppression
   placement), so a clean round still gets a summary.
5. Every round's findings appended to `critic-findings.md` — round 1 onward
   — must carry the hidden key marker alongside the existing prose.
6. `reconcile` must filter both `prev` and `curr` to BLOCKER/MAJOR before
   classifying; MINOR/OBS entries (present when the source is a Finding
   Table) are dropped, not reconciled.
7. `reconcile` must count key occurrences per round (multiset semantics), so
   two findings sharing a key in `curr` against one in `prev` nets as one
   `persisted`, one `new`.

## Non-Functional Requirements

1. `finding_key` must not change `critic_hash`'s existing return value for
   existing PR-comment-dedup callers.
2. `reconcile` must be deterministic: identical `(prev, curr)` multisets
   always yield identical classification, independent of list order.

## Test Strategy

| Type        | Rationale                                                     |
|-------------|------------------------------------------------------------------|
| Unit        | fixed/persisted/new classification, order-independence; empty prev/curr edges |
| Unit        | mixed-severity input excludes MINOR/OBS (FR-6); duplicate-key multiset (FR-7) |
| Unit        | `critic_hash`/`finding_key` agree (FR-1); marker round-trip (FR-3) |
| Integration | Step 7 + Step 7a fixture, 2 rounds incl. a clean round 1: summary + count + keys |
| Regression  | Existing dedup tests unchanged and green                        |

## Acceptance Criteria

- Round-1/round-2 lists differing by one fixed + one new BLOCKER reconcile to
  one `fixed`, one `new`, zero `persisted`.
- `critic-findings.md` every round's section, starting at round 1, includes
  each finding's stable key.
- Existing ticket-0031 dedup tests pass unchanged.

## Open Questions

None.

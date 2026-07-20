# Solution

**Ticket**: 0062
**Title**: Stable critic finding IDs

## Approach

Extract the `(file, line, severity, code)` key from
`comment_deduplicator.critic_hash` into a shared `finding_key()` helper in
`gates/finding.py`. Add `gates/critic_reconciler.py` with `reconcile()`,
operating on parsed `Finding` lists with BLOCKER/MAJOR-only, multiset
semantics. Persist each round's keys as a hidden marker (mirroring the
existing PR-comment marker convention) so the next round harvests `prev`
without re-parsing prose. Wire into `build-ticket.md` Step 7 (round 1,
entry) and Step 7a (repair rounds, entry — before its skip-to-7c branch).

## Components

| Component | Responsibility |
|-----------|-----------------|
| `gates/finding.py` — `finding_key(f)` | Single source for `(file, line, severity, code)`; `critic_hash` calls it |
| `gates/critic_reconciler.py` — `reconcile(prev, curr)`, `marker_for_key()`, `harvest_keys()` | Filters to BLOCKER/MAJOR, classifies by `finding_key` with multiset counting; marker write/harvest for the round-trip |
| `build-ticket.md` Step 7 + 7a edit | Each round: harvest `prev` from the prior round's markers, call `reconcile`, announce the summary — placed at Step 7a's entry, ahead of its skip-to-7c check |
| `critic-findings.md` append format | Each finding line gains a trailing `<!-- harness-finding-key file:line:severity:code -->` marker — additive, invisible in rendered markdown |
| `tests/test_0062_critic_reconciler.py` | Unit/integration tests per Test Plan |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Reconciler key is the plain tuple, not the sha256 hash | Needs to be logged/displayed (`"file.py:12:BLOCKER"`); hashing stays PR-dedup-only |
| `code` = existing Panel/Dimension label, unchanged | Already populated by `_finalize`/`critic_hash` today — no new taxonomy needed |
| `prev` harvested from a hidden marker, not re-parsed prose | An HTML-comment marker can't collide with `_HEADER_RE`/`_FILELINE_RE`/`_TABLE_ROW_RE`; mirrors `comment_deduplicator.marker_for`'s proven round-trip pattern instead of inventing a second one |
| Multiset classification (FR-7) | Honest about same-key collisions within a round instead of silently dropping duplicates |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-2        | Unit        | fixed/persisted/new classification, order-independence |
| FR-2        | Unit        | round-1 (empty prev) -> all new; final round (empty curr) -> all fixed |
| FR-6        | Unit        | mixed-severity input excludes MINOR/OBS from all buckets |
| FR-7        | Unit        | duplicate-key multiset counting within one round |
| FR-1        | Unit        | `critic_hash` and `finding_key` agree on the same Finding |
| FR-3        | Unit        | marker round-trip: write, harvest, key matches original Finding |
| FR-4,5      | Integration | Step 7 + Step 7a fixture, 2 rounds incl. a clean round 1: summary + count + keys present |
| NFR-1       | Regression  | Existing dedup tests unchanged and green |

## Tradeoffs

- **Reuses the existing Panel/Dimension `code`, not a new taxonomy**: two
  findings sharing file:line:severity:Panel/Dimension still collide (same
  line, same panel, same dimension, same severity — rare) — accepted, tracked
  via FR-7's multiset semantics rather than silently merged.
- **`prev` is harvested from a marker rather than reusing in-context Finding
  objects**: slightly more I/O per round, but keeps each round stateless and
  robust across session boundaries.

## Risks

- `critic-findings.md` format changes could conflict with ticket 0067 (also
  unbuilt) if it assumes the current prose-only format — mitigate by keeping
  the change additive regardless of build order.
- `gates/finding.py` is shared with ticket 0031's PR-comment path —
  `finding_key` must keep `critic_hash`'s existing return value
  byte-identical (regression test asserts unchanged hashes).

## Implementation Order

1. Add `finding_key()` to `gates/finding.py`; repoint `critic_hash` to use it;
   regression-test existing dedup hashes are unchanged.
2. Add `gates/critic_reconciler.py`: `reconcile()`, `marker_for_key()`,
   `harvest_keys()` + unit tests (incl. marker round-trip).
3. Extend `critic-findings.md` append format (additive marker, all rounds) +
   integration test.
4. Wire harvest + `reconcile` + summary into `build-ticket.md` Step 7 entry
   and Step 7a entry (ahead of its skip-to-7c branch).
5. Update `harness-reference.md` "Critic findings file" section to document
   the new marker.

# Solution

**Ticket**: 0051
**Title**: Checkpoint invalidation on spec edits and post-rebase re-gating

## Approach

Extend the checkpoint JSON with a per-spec hash map (sha256 of the spec source),
filter stale entries at read time inside server.py's checkpoint tool, and update the
two flow docs: Step 3 announces invalidations; deliver Step 7 re-gates before deciding
status. ticket 0008's pre-deliver guard remains the delivering ticket's freshness
mechanism — this ticket covers the bystander worktrees and resumed builds.

## Components

| Component | Responsibility |
|-----------|----------------|
| server.py checkpoint tool | Hash map on write; mismatch filtering + invalidated list on read |
| build-ticket.md Step 3 | Invalidation announcement wording |
| deliver-ticket.md Step 7 | Re-gate step; conditional downgrade; clean-note wording |
| tests | Round-trip, mismatch, legacy-format, docs greps |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| sha256 of spec file content | Deterministic, cheap, no mtime flakiness across clones |
| Filter at read (server-side) | One enforcement point; flows stay simple consumers |
| Legacy files invalidate fully | Fail toward re-verification, never toward stale skips |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Write stores hashes for specs and task file |
| FR-2 | Unit | Mismatch excluded and listed as invalidated; match retained |
| FR-3 | Unit | Docs grep: Step 3 announcement present |
| FR-4 | Unit | Docs grep: Step 7 re-gate + conditional downgrade wording |
| FR-5 | Unit | Legacy checkpoint file: zero completed, invalidated announcement |

## Tradeoffs

- **Chose file-hash invalidation over DAG-dependency invalidation because**: the
  common failure is the edited spec itself; cascading invalidation is a larger design
  with its own ticket-worth of semantics.
- **Accepting risk of**: re-running specs on cosmetic spec edits — cheap and safe.

## Risks

- Step 7 re-gates several worktrees after one delivery; gate runs are per-worktree
  fail-fast and only triggered by an actual delivery, so cost is bounded.

## Implementation Order

1. server.py checkpoint hash write/read + tests.
2. build-ticket Step 3 wording.
3. deliver-ticket Step 7 re-gate logic and wording.
4. Docs tests; full suite.

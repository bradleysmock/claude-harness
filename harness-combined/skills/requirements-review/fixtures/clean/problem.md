# Problem Statement

**Ticket**: FIXTURE
**Title**: Rate limiting (clean fixture)

## Problem

The public API has no rate limiting, so a single client can exhaust capacity for
everyone else.

## Impact

- One noisy client degrades latency for all other clients.
- Operators cannot cap per-client usage.

## Success Criteria

- Each client is limited to a configurable request rate.
- Requests over the limit receive a clear rejection with a retry hint.
- Operators can configure the per-client limit without a redeploy.

## Out of Scope

- Global (cross-client) rate limiting.

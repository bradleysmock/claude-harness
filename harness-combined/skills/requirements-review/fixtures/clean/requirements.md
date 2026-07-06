# Requirements

**Ticket**: FIXTURE
**Title**: Rate limiting (clean fixture)

## Functional Requirements

1. The system must reject requests from a client that exceed 100 requests per 60-second window.
2. The system must return HTTP 429 with a `Retry-After` header on a rejected request.
3. The system must read the per-client limit from configuration reloaded without a redeploy.

## Acceptance Criteria

- A client sending 101 requests within 60 seconds receives HTTP 429 on the 101st.
- A rejected response includes a `Retry-After` header with a positive integer value.
- Changing the configured limit takes effect within 5 seconds without a process restart.

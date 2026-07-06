# Requirements

**Ticket**: FIXTURE
**Title**: Upload retry policy (consistency-defect fixture)

## Functional Requirements

1. The system must retry a failed upload automatically.
2. The system must never retry a failed upload.
3. The system must log every upload attempt.

## Acceptance Criteria

- The retry behavior is observable in the logs.
- Each upload attempt produces exactly one log line.

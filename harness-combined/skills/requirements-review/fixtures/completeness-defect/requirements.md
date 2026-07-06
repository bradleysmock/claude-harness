# Requirements

**Ticket**: FIXTURE
**Title**: Upload retry (completeness-defect fixture)

## Functional Requirements

1. The system must retry a failed upload up to 3 times with exponential backoff.
2. The system must report the true count of successfully uploaded files in the batch summary.

## Acceptance Criteria

- A upload that fails twice then succeeds is reported as uploaded after 3 attempts.
- A batch of 10 files where 2 fail permanently reports "8 of 10 uploaded".

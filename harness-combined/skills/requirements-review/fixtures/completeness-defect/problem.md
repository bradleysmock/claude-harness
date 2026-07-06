# Problem Statement

**Ticket**: FIXTURE
**Title**: Upload retry (completeness-defect fixture)

## Problem

The uploader drops files when the network blips and the operator has no idea it
happened.

## Impact

- Uploads fail silently and the operator is never notified.
- Partial batches are reported as complete.

## Success Criteria

- Failed uploads are retried.
- A completed batch reports the true count of uploaded files.

## Out of Scope

- Changing the storage backend.

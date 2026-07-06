Roll back a **delivered** ticket by reverting its merge commit with a standardized `git revert`. This is a thin entry point — all logic lives in `skills/rollback/SKILL.md`.

## Usage

```
/rollback XXXX [--dry-run]
```

- `XXXX` — a ticket number matching `^[0-9]{4}(-[a-z0-9-]+)?$` (required). A bare four-digit number (`0020`) or a number-with-slug (`0020-rollback-skill`) are both accepted; the slug suffix is ignored.
- `--dry-run` — optional. Preview the merge commit that would be reverted and exit without making any git change.

## Dispatch

This command carries **no logic of its own**. Pass `$ARGUMENTS` through verbatim and load `skills/rollback/SKILL.md`, then follow that procedure exactly.

Fail-closed input validation is the **skill's first step** (Step 0): an invalid or empty argument stops before any git command runs. Ticket-status resolution, unambiguous merge-commit lookup, subject verification, operator confirmation, the clean-tree pre-flight, and the revert itself are all defined there — do not re-implement any of them here.

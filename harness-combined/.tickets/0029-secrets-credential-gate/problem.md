# Problem Statement

**Ticket**: 0029
**Title**: Secrets/Credential Gate
**Date**: 2026-06-21

## Problem

The harness has no automated check preventing committed or staged code containing secrets, API keys,
tokens, or high-entropy strings from reaching delivery. A developer can merge code with accidentally
hardcoded credentials and the pipeline will not catch it. This is the highest-severity class of
defect and should fail the pipeline as early as possible.

## Impact

- Harness operators (lead engineers) face credential exposure risk every time code passes
  through the deliver pipeline without a secrets scan.
- Without a fast-fail gate, a leaked secret may reach a merge or a published artifact before
  it is noticed, requiring credential rotation and potentially public disclosure.
- The absence of this gate also means no structured record of what was found and redacted,
  making incident response harder.

## Success Criteria

- A `secrets-scan` gate runs as the first gate in the pre-deliver suite.
- The gate detects API keys, tokens, passwords, and high-entropy strings in staged and committed
  files within the ticket's worktree.
- When a secret is detected, the gate exits non-zero and blocks delivery.
- Findings are written to `gate-findings.md` with file path, line range, and redacted match context.
- Known false positives can be suppressed via a `.gitleaks.toml` (or equivalent) allow-list in
  the project root.
- The gate is skipped gracefully (non-blocking warning) when the scanner binary is not installed,
  rather than erroring the entire pipeline.

## Out of Scope

- Scanning git history beyond the current branch's diff (historical secret rotation is a separate
  concern).
- Automatic secret revocation or rotation.
- CI/CD integration outside the harness deliver pipeline.

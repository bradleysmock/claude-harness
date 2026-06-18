---
description: "Phase 3 — generate characterization tests that record current behavior as a refactoring net, verify green against unmodified source, then freeze the net (read-only)."
argument-hint: "<unit path>"
---

# Phase 3 · Characterization net — `$ARGUMENTS`

Use the **generator** agent. Generate characterization tests at the stable seams of `$ARGUMENTS`. These RECORD current observable behavior to serve as a refactoring net — they do NOT assert correctness.

- Test through the seam, not internals. Capture representative inputs incl. boundaries and error paths.
- Where current output is surprising, do NOT "fix" it — record it and add `// CHARACTERIZED: possibly-incorrect` with a one-line note for the human.
- Header every file: "Characterization tests — record current behavior, not validated correctness."

**Gate (X):** run the suite against UNMODIFIED source; it must be green.

**Freeze:** once green, run `scripts/freeze-net.sh <test-file-glob>` to record the net's files + checksums in `.test-harness/frozen-net.txt`. From now the net is immutable — the PreToolUse hook will block any edit to it. Log every `possibly-incorrect` marker for the Phase 4 oracle review.

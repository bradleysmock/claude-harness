---
description: "Phase 5 — lock module/service seams with contract tests covering input acceptance, output shape, error contract, and invariants."
argument-hint: "<seam / boundary path>"
---

# Phase 5 · Contract tests — `$ARGUMENTS`

Use the **generator** agent. At each module or service boundary identified as a seam in `$ARGUMENTS`, write contract tests that lock the interface: input acceptance, output shape, error contract, and the invariants consumers rely on. For cross-service seams, structure them as consumer-driven contracts.

**Gate (V):** invoke the **verifier** to confirm the contracts cover shape, error paths, and invariants — not just the happy shape.

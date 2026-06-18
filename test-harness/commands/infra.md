---
description: "Phase 1 — stand up the test harness end-to-end with one smoke test and the mutation engine wired; prove the loop closes before scaling."
argument-hint: "<language or stack hint, optional>"
---

# Phase 1 · Harness + smoke test

Use the **generator** agent. Stand up the harness for this repo (`$ARGUMENTS`):

- Choose runner, assertion library, and mocking/fixture strategy (one-line justification each).
- Configure coverage instrumentation AND install the mutation engine now (Stryker for JS/TS, PIT for JVM, mutmut/cosmic-ray for Python). Confirm it runs on a single file via `scripts/mutation-diff.sh`.
- Write exactly ONE trivial smoke test against a pure unit from the seam map.
- Wire runner + coverage into CI as a gating check.

**Exit gate (X):** CI green on one test; coverage emitted; mutation engine runs on one file. Stop here until all three hold — do not generate more tests.

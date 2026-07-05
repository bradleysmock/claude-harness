# Solution

**Ticket**: 0052
**Title**: Align hook gates with MCP gates; record resolutions in failure memory

## Approach

Make the two hook-command fixes directly, then codify parity as data: a per-language
command table in harness-reference.md plus a drift test that parses both hook source
and gate source for the command strings. Extend SQLiteFailureMemory with a nullable
resolution column and thread it through record, narratives, and the Step 4e recording
instruction.

## Components

| Component | Responsibility |
|-----------|----------------|
| hooks/stop_full_gate.py | -race on Go tests |
| hooks/post_write_gate.py | Project-root npx --no-install eslint resolution with fallback |
| context/harness-reference.md | Side-by-side hook/gate command table |
| tests/test_0052_hook_gate_drift.py | Command parity drift guard |
| memory.py + server.py memory tool | resolution column, record param, narrative line |
| build-ticket.md Step 4e | Pass fix summary on passed-outcome records |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Drift test over shared config | Hooks must stay import-free standalone scripts; a test is the cheapest sync |
| Nullable column + guarded ALTER | Zero-migration path for existing memory.db files |
| Upward package.json search | Deterministic project-root resolution without config |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Command construction includes -race |
| FR-2 | Unit | Local-only eslint fixture lints; no-eslint fixture skips quietly |
| FR-3 | Unit | Drift test: doc table matches hook and gate source commands |
| FR-4 | Unit | record with resolution persists; legacy rows unaffected; docs grep on Step 4e |
| FR-5 | Unit | Narrative rendering includes resolution when present |

## Tradeoffs

- **Chose doc-table-plus-drift-test over extracting shared command constants
  because**: hooks run as standalone python3 scripts without the package on sys.path;
  imports would complicate deployment more than a test costs.
- **Accepting risk of**: resolution summaries varying in quality — any one-liner beats
  the current nothing, and retrieval consumers are models.

## Risks

- ALTER TABLE on live databases — guard with a column-existence pragma check and
  tests against a pre-change fixture db.

## Implementation Order

1. Hook fixes (-race, npx resolution) + unit tests.
2. memory.py resolution column + tool param + narrative line + tests.
3. build-ticket Step 4e wording.
4. harness-reference command table + drift test.

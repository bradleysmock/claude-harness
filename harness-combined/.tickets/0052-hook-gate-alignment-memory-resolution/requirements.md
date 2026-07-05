# Requirements

**Ticket**: 0052
**Title**: Align hook gates with MCP gates; record resolutions in failure memory

## Functional Requirements

1. stop_full_gate's Go test command must include -race, matching the MCP gate.
2. post_write_gate's JS/TS lint must resolve eslint via npx --no-install from the
   written file's project root (nearest package.json directory), falling back to a
   PATH eslint, and skipping silently only when neither exists.
3. context/harness-reference.md must document the hook and MCP gate command sets
   side-by-side per language, and a drift test must assert the documented commands
   match the source of both layers.
4. memory(action="record") must accept an optional resolution field, stored with the
   record; build-ticket.md Step 4e must instruct passing a one-line fix summary when
   recording a passed outcome.
5. memory retrieval narratives must include the resolution line when present.

## Non-Functional Requirements

1. Hook latency budget unchanged: per-write lint stays within the existing 20-second
   tool timeout; project-root resolution must be a simple upward search.
2. memory.db change must be backward compatible (nullable column added via
   CREATE TABLE IF NOT EXISTS migration or ALTER guarded by pragma check).

## Test Strategy

| Type | Rationale                                                          |
|------|----------------------------------------------------------------------|
| Unit | Hook command construction (race flag, npx resolution, fallback, skip) |
| Unit | Memory: resolution round-trip, legacy rows retrievable, narrative rendering |
| Unit | Drift test comparing documented commands to hook/gate source          |

## Acceptance Criteria

- The Stop hook's Go test invocation contains -race.
- On a fixture with only node_modules/.bin/eslint, a .ts write triggers lint findings.
- A recorded passed failure with a resolution renders the resolution in retrieval; old
  rows without one still render.
- The drift test fails when a hook command diverges from the reference table.

## Open Questions

- None.

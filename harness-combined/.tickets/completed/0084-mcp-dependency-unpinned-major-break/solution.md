# Solution

**Ticket**: 0084
**Title**: Pin mcp dependency below 2.0 to prevent server crash on fresh venv install

## Approach

Two small, coupled fixes. First, bound `requirements.txt`'s `mcp` dependency
to the 1.x line `server.py` actually targets, so a fresh install can never
resolve to the incompatible 2.x `MCPServer` API. Second, correct
`bin/harness-server`'s health check to probe the exact import `server.py`
needs (`mcp.server.fastmcp.FastMCP`), not a bare `import mcp` — the bare
check is a false negative under 2.x (only the submodule is gone), which is
why a machine already stuck on 2.x never self-heals today. Neither fix
touches `server.py` itself.

## Components

| Component | Change |
|---|---|
| `requirements.txt` | `mcp>=1.0` → `mcp>=1.0,<2.0` |
| `bin/harness-server` (line 31) | health-check import target: `import mcp` → `from mcp.server.fastmcp import FastMCP` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Version ceiling (`<2.0`), not an exact pin | Keeps receiving 1.x patch/minor releases without a ticket per release; excludes only the breaking major line |
| Fix the health-check import target, not add a second check | The launcher already has exactly one gate (`||` chain at line 31); making its existing probe accurate is simpler and lower-risk than adding new checks |
| Fix the constraint + health check, not migrate to `MCPServer` | Migration is a larger, separate effort (out of scope); these two changes fully prevent and repair the crash without touching server logic |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1/FR-4   | Regression  | `requirements.txt`'s `mcp` line reads exactly `mcp>=1.0,<2.0`; every other line is byte-identical to the pre-change file |
| FR-2        | Integration (network, skip if offline) | `bin/harness-server` launched against a deleted `.venv` bootstraps against the real PyPI index and starts the server without a traceback — the one scenario that must hit the real registry, since it is the real production path |
| FR-3        | Integration (hermetic) | A `.venv` pre-seeded with a local fixture package named `mcp` (bare `__init__.py`, no `server.fastmcp` submodule — no network, no real 2.x download) is launched via `bin/harness-server`; the corrected health check detects the broken import, reinstalls the real (now-pinned) `mcp`, and the server starts clean afterward |

## Tradeoffs

- **Chose a version ceiling + health-check fix over migrating to `MCPServer`
  because**: both changes are small and zero-risk; migrating the API is
  unrelated scope with its own testing burden.
- **Accepting risk of**: none beyond ordinary dependency/health-check
  maintenance — both changes only narrow an existing constraint and correct
  an existing check; neither can break a currently-passing install.

## Risks

- A machine already stuck on `mcp` 2.x needs one more `bin/harness-server`
  launch after this ships (to trigger the corrected health check) before it
  self-heals — a single launch cycle is required, not instant on merge.
- The health check's import target (`from mcp.server.fastmcp import
  FastMCP`) now duplicates `server.py`'s own import line in a second file.
  If `server.py`'s import ever changes, the health check can go stale again
  silently. Mitigate with a same-line comment on the check pointing back to
  `server.py`'s import as the source of truth, so a future edit to one is
  more likely to prompt updating the other.

## Implementation Order

1. Build the local hermetic fixture package (bare `mcp/__init__.py`, no
   `server` submodule) used by the FR-3 test.
2. Integration tests (red first): the hermetic FR-3 test, seeding a `.venv`
   with the fixture and asserting `bin/harness-server` currently does NOT
   self-heal; the network FR-2 test, with an explicit `--no-cache-dir` pip
   install against the current unbounded pin plus a version assertion
   confirming it resolves `mcp>=2.0` (guards against a stale local cache
   masking the real failure), asserting the server currently crashes.
3. Edit `requirements.txt`'s `mcp` line to `mcp>=1.0,<2.0`.
4. Edit `bin/harness-server` line 31's health-check import target, with a
   comment noting it must track `server.py`'s own import.
5. Re-run both integration tests to confirm they now pass; diff
   `requirements.txt` to confirm no other line changed.

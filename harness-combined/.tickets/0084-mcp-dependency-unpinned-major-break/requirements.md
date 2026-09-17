# Requirements

**Ticket**: 0084
**Title**: Pin mcp dependency below 2.0 to prevent server crash on fresh venv install

## Functional Requirements

1. `requirements.txt`'s `mcp` line must exclude the 2.x release line that
   renamed `FastMCP` to `MCPServer`, while still allowing 1.x patch/minor
   updates: the pin must read `mcp>=1.0,<2.0`.
2. A fresh bootstrap of `bin/harness-server` (no existing `.venv`, or a
   `.venv` whose health check fails) must install an `mcp` release that
   satisfies `<2.0`, so `server.py`'s
   `from mcp.server.fastmcp import FastMCP` import must succeed.
3. `bin/harness-server`'s health check (line 31) must probe the exact import
   `server.py` depends on (`from mcp.server.fastmcp import FastMCP`), not a
   bare `import mcp` — so a venv that already has `mcp` 2.x installed is
   correctly detected as broken and triggers a reinstall on the next launch,
   rather than passing a check that only proves the top-level package
   exists.
4. Every other line in `requirements.txt` must remain unchanged.

## Non-Functional Requirements

1. The fix must be a version-constraint change plus a one-line health-check
   correction — no other code in `server.py` or elsewhere changes.

## Test Strategy

| Type        | Rationale                                                          |
|-------------|---------------------------------------------------------------------|
| Regression  | `requirements.txt`'s `mcp` line matches the exact bounded pin, and no other line differs from the pre-change file |
| Integration (network, skip if offline) | A fresh `bin/harness-server` launch (deleted `.venv`) bootstraps against the real PyPI index, installs `mcp<2.0`, and the launcher's own `exec "$PY" server.py` starts without a traceback — this is the one scenario that must exercise the real registry, since it is the actual production bootstrap path |
| Integration (hermetic, no network) | A venv seeded with a local fixture package literally named `mcp` (an `__init__.py` only, no `server.fastmcp` submodule — reproducing "bare `import mcp` succeeds, the submodule import doesn't" without needing a real 2.x release) triggers `bin/harness-server`'s corrected health check to reinstall on the next launch, and the launcher starts clean afterward |

## Acceptance Criteria

- `requirements.txt`'s `mcp` line reads `mcp>=1.0,<2.0`; the rest of the file
  is byte-for-byte unchanged.
- `bin/harness-server`'s health check imports `mcp.server.fastmcp.FastMCP`
  specifically, not just the bare `mcp` package.
- A fresh `bin/harness-server` launch against a deleted `.venv` starts the
  server without error.
- A `.venv` pre-seeded with `mcp` 2.x is detected as broken and reinstalled
  by `bin/harness-server` on the next launch, after which the server starts
  without error.

## Open Questions

None.

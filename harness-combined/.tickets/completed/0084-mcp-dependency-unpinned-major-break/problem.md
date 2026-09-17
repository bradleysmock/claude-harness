# Problem Statement

**Ticket**: 0084
**Title**: Pin mcp dependency below 2.0 to prevent server crash on fresh venv install
**Date**: 2026-09-17

## Problem

`requirements.txt` pins `mcp>=1.0`, no upper bound. `mcp` shipped a 2.x line
renaming `FastMCP` to `MCPServer`, but `server.py:22` still does
`from mcp.server.fastmcp import FastMCP`. A fresh bootstrap resolving to
2.x crashes the server at import (`ModuleNotFoundError`), surfacing as
`CONNECTION_CLOSED`. Worse, `bin/harness-server`'s health check runs a bare
`import mcp`, which still succeeds under 2.x (only the submodule is gone) —
so an already-broken venv is never detected or re-installed.

## Impact

- Confirmed via Claude Code's own MCP logs: two headless `autopilot` builds
  this session (0081, 0082) hit this exact traceback, losing the harness
  MCP server for that build; a live session catching the same failure never
  recovers, since the client doesn't retry after an initial handshake fails.
- Recurs on any fresh venv landing on `mcp` 2.x+ (new machine, deleted
  `.venv`, `pip install --upgrade`), and self-perpetuates once it happens,
  since the weak health check never re-triggers a reinstall.

## Success Criteria

- `requirements.txt` bounds `mcp` below the 2.x line.
- A fresh bootstrap (no `.venv`) installs working `mcp` 1.x and starts clean.
- A venv already stuck on `mcp` 2.x self-heals on the *next* launch: the
  health check must probe the actual import server.py needs, not bare presence.
- No other `requirements.txt` line changes.

## Out of Scope

- Migrating `server.py` to the `mcp` 2.x `MCPServer` API.
- Recovering a session's own already-failed connection without a new launch
  (self-heal applies next launch, not mid-session), and the unrelated
  orphaned `server.py` processes noticed during investigation.

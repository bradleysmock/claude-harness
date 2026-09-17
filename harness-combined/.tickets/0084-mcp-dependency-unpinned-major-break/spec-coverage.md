# Spec Coverage Map

**Ticket**: 0084-mcp-dependency-unpinned-major-break
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | `requirements.txt`'s `mcp` line must exclude the 2.x release line that | 0084-mcp-dependency-unpinned-major-break-requirements-pin |
| FR-2 | FR | A fresh bootstrap of `bin/harness-server` (no existing `.venv`, or a | 0084-mcp-dependency-unpinned-major-break-health-check |
| FR-3 | FR | `bin/harness-server`'s health check (line 31) must probe the exact import | 0084-mcp-dependency-unpinned-major-break-health-check |
| FR-4 | FR | Every other line in `requirements.txt` must remain unchanged. | 0084-mcp-dependency-unpinned-major-break-requirements-pin |
| AC-1 | AC | `requirements.txt`'s `mcp` line reads `mcp>=1.0,<2.0`; the rest of the file | 0084-mcp-dependency-unpinned-major-break-requirements-pin |
| AC-2 | AC | `bin/harness-server`'s health check imports `mcp.server.fastmcp.FastMCP` | 0084-mcp-dependency-unpinned-major-break-health-check |
| AC-3 | AC | A fresh `bin/harness-server` launch against a deleted `.venv` starts the | 0084-mcp-dependency-unpinned-major-break-health-check |
| AC-4 | AC | A `.venv` pre-seeded with `mcp` 2.x is detected as broken and reinstalled | 0084-mcp-dependency-unpinned-major-break-health-check |

## Uncovered

None.

# harness-pi

A Pi package that ports the **harness-combined** Claude Code plugin to
[pi](https://pi.dev). It reuses the original plugin's Python engine
(`server.py`, `gates/`, `hooks/`, `ticket.py`, …) unchanged and bridges the
Claude-Code-specific extension points into Pi's extension API.

## Layout

```
harness-pi/
├── package.json                 # pi package manifest (extensions/prompts/skills)
├── extensions/
│   ├── harness-config.ts        # locates harness-combined, injects CLAUDE_PLUGIN_ROOT
│   ├── mcp-client.ts            # minimal MCP stdio JSON-RPC client
│   ├── mcp-bridge.ts            # launches server.py, registers its 12 tools as pi tools
│   ├── hook-bridge.ts           # maps pi tool_call/tool_result/agent_settled -> the 5 py hooks
│   └── subagent.ts              # `task` tool: spawns isolated pi runs for critic / requirements-analyst
├── prompts/                     # 30 slash commands converted to pi prompt templates
└── scripts/
    └── convert-commands.mjs     # regenerates prompts/ from harness-combined/commands/
```

Skills are consumed directly from `../harness-combined/skills` (Pi supports the
Agent Skills standard natively), and `CLAUDE.md` is loaded by Pi as a context
file with no changes.

## Setup

1. Keep `harness-combined/` next to this package (default), or set
   `HARNESS_COMBINED_ROOT` to its absolute path.
2. Bootstrap the Python engine's venv once (creates `harness-combined/.venv`):
   ```bash
   bash ../harness-combined/bin/harness-server </dev/null   # Ctrl-C after "bootstrap complete"
   ```
3. Install the package into pi:
   ```bash
   pi install -l git:...            # or add to settings.json "packages"/"extensions"
   # for local dev, point pi at it directly:
   pi -e ./extensions/mcp-bridge.ts -e ./extensions/hook-bridge.ts -e ./extensions/subagent.ts
   ```
4. Regenerate prompt templates if the upstream commands change:
   ```bash
   node scripts/convert-commands.mjs
   ```

## Claude Code → Pi mapping

| Claude Code mechanism | Pi mechanism (here) |
|-----------------------|---------------------|
| `mcpServers` (server.py, 12 tools) | `mcp-bridge.ts` → `pi.registerTool()` per MCP tool |
| `PreToolUse` (Write\|Edit\|MultiEdit) | `tool_call` event, blocks on hook exit 2 |
| `PostToolUse` | `tool_result` event |
| `Stop` | `agent_settled` event |
| subagents + Task | `subagent.ts` `task` tool (isolated `pi -p`) |
| `${CLAUDE_PLUGIN_ROOT}` | injected env for subprocesses; resolved to a literal in prompts |
| slash commands (`$ARGUMENTS`) | prompt templates (`$ARGUMENTS` supported natively) |
| skills / CLAUDE.md | used as-is |

### Tool-name / schema translation

- pi `write` `{path, content}` → CC `Write` `{file_path, content}`
- pi `edit` `{path, edits:[{oldText,newText}]}` → CC `Edit`/`MultiEdit`
  `{file_path, ...old_string/new_string}`
- agent frontmatter tools `Read,Grep,Glob,Write,Edit,Bash,LS` →
  `read,grep,find,write,edit,bash,ls`

## Known gaps / follow-ups

- **Stop-hook feedback is advisory.** CC re-prompts the model when a Stop hook
  exits 2; Pi's `agent_settled` fires after the turn has settled, so
  `hook-bridge.ts` surfaces gate failures as a notification instead of forcing
  another turn. If you need enforcement, convert it to inject a follow-up
  message via `pi.sendUserMessage(..., { deliverAs: "followUp" })`.
- **MCP schema pass-through** forwards FastMCP's JSON Schema verbatim as the pi
  tool parameter schema. If any harness tool uses schema features pi's
  validator rejects, tighten it in `registerTools()`.
- **Subagent parity.** `subagent.ts` spawns `pi -p` with `--append-system-prompt`
  and a restricted `--tools` list. It does not yet stream progress or report
  token usage like the reference example; add `onUpdate` rendering if desired.
- **Parallel writes.** In pi's default parallel tool mode, `tool_call` handlers
  are preflighted sequentially, so the blocking guard is safe; verify the
  Python hooks tolerate concurrent invocation if you enable heavy parallelism.

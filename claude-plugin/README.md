# claude-harness

A Claude Code plugin that installs a structured, two-checkpoint SDLC harness: slash commands, expert review panels, polyglot validation hooks, and a working agreement.

## Installation

### Via Claude Code plugin system

```bash
# Install from a plugin directory for local testing
claude --plugin-dir ./claude-plugin

# Or install from the marketplace (once published)
/plugin install <marketplace-url>
```

### Manual setup after installing

The plugin automatically activates commands, agents, and hooks. Two things must be done manually:

1. **Copy `CLAUDE.md` to your project root** (the plugin cannot install files outside the plugin directory):
   ```bash
   cp "$(claude plugin path claude-harness)/CLAUDE.md" ./CLAUDE.md
   ```
   Skip this step if your project already has a `CLAUDE.md`.

2. **Add permission allowlist to your project's `.claude/settings.json`** — the plugin cannot ship a `settings.json` with `permissions` entries. Copy the allowlist from the [Permission Reference](#permission-reference) section below and merge it into your project's `.claude/settings.json`.

## What the plugin provides

| Path (relative to plugin root) | Purpose |
|-------------------------------|---------|
| `commands/*.md` | 10 slash commands for the full pipeline |
| `agents/critic.md` | Read-only critic subagent |
| `hooks/hooks.json` | Hook wiring (pre-write guard, post-write linter, stop-gate suite) |
| `hooks/pre_write_guard.py` | Pre-write code shape scanner (polyglot) |
| `hooks/post_write_gate.py` | Post-write per-file linter/SAST |
| `hooks/stop_full_gate.py` | Stop-event full gate suite |
| `context/rules/` | Universal + per-language code generation rules |
| `context/panels/` | 6 expert review panels loaded on demand |
| `context/critic-brief.md` | Shared brief for all critic invocations |
| `CLAUDE.md` | Working agreement (copy to project root) |

## Workflow

Work runs autonomously between two human checkpoints.

```
/problem  →  [autonomous: problem → requirements → solution → critic loop]
                                                                    ↓
                                                       CHECKPOINT 1: approve to implement
                                                                    ↓ approved
/implement  →  [autonomous: worktree → TDD → critic/review loop]
                                                          ↓
                                             CHECKPOINT 2: approve to merge
                                                          ↓ approved
/merge
```

## Slash commands

| Command | Purpose |
|---------|---------|
| `/claude-harness:problem` | Entry point: clarity check → problem → requirements → solution → critic loop → Checkpoint 1 |
| `/claude-harness:implement` | TDD implementation in a worktree → gate → critic/review loop (max 2 rounds) → Checkpoint 2 |
| `/claude-harness:merge` | Merge approved branch into main, remove worktree |
| `/claude-harness:gate` | Manual gate runner: ruff + mypy + bandit + pytest |
| `/claude-harness:score-spec` | Validates requirements.md and solution.md specificity |
| `/claude-harness:requirements` | Manual requirements pass |
| `/claude-harness:solution` | Manual solution pass |
| `/claude-harness:refine` | Iterate on an existing solution |
| `/claude-harness:review` | Manual code review |
| `/claude-harness:critique` | Expert panel code review — loads panels based on file scope |

## Polyglot gates

Hooks dispatch on file extension; the Stop hook detects stacks from project-root markers.

| Stack | Marker(s) | Pre-write rules | Post-write gate | Stop-gate suite |
|-------|-----------|-----------------|-----------------|-----------------|
| Python | `pyproject.toml` / `*.py` | `rules/python.md` | ruff + bandit | ruff + bandit + mypy + pytest |
| JavaScript | `package.json` | `rules/javascript.md` | eslint | eslint + `npm test` |
| TypeScript | `tsconfig.json` / `*.ts` | both above | eslint | eslint + tsc + `npm test` |
| Go | `go.mod` | `rules/go.md` | gofmt | gofmt + `go vet` + `go test` |
| Rust | `Cargo.toml` | `rules/rust.md` | rustfmt | `cargo fmt --check` + clippy + `cargo test` |

Missing tools are skipped gracefully.

## Expert panels

Panels are loaded on demand by `/claude-harness:critique` and critic agents in `/claude-harness:problem` and `/claude-harness:implement`.

| Panel | Loaded when | Experts |
|-------|-------------|---------|
| Core | Always | Martin, Ousterhout, Fowler, Beck, McGraw, Evans |
| Python | `*.py` files in scope | Hettinger, Beazley |
| HTTP/API | Route handlers in scope | Gross, Nottingham |
| UI | Templates or static assets in scope | Keith, Pickering, Wathan, Frost |
| AI/LLM | LLM client code in scope | Willison |
| Secondary | Primary panel impasse only | Ramalho, Soueidan |

## Permission Reference

The plugin cannot ship a `settings.json` with `permissions` entries. Add these to your project's `.claude/settings.json` to avoid repeated permission prompts:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
      "Bash(git branch:*)", "Bash(git show:*)",
      "Bash(git worktree list:*)", "Bash(git worktree add:*)", "Bash(git worktree remove:*)",
      "Bash(git add:*)", "Bash(git commit:*)", "Bash(git checkout:*)",
      "Bash(git rebase:*)", "Bash(git merge:*)",
      "Bash(ls:*)", "Bash(mkdir:*)",
      "Bash(pytest:*)", "Bash(ruff:*)", "Bash(mypy:*)", "Bash(bandit:*)",
      "Bash(python3 -m pytest:*)", "Bash(python -m pytest:*)",
      "Bash(npm test:*)", "Bash(npm run test:*)",
      "Bash(npx --no-install eslint:*)", "Bash(npx --no-install tsc:*)",
      "Bash(eslint:*)", "Bash(tsc:*)",
      "Bash(go test:*)", "Bash(go vet:*)", "Bash(go build:*)", "Bash(gofmt:*)",
      "Bash(cargo test:*)", "Bash(cargo clippy:*)", "Bash(cargo check:*)",
      "Bash(cargo fmt:*)", "Bash(rustfmt:*)"
    ],
    "deny": [
      "Bash(git push:*)",
      "Bash(rm -rf:*)",
      "Bash(git reset --hard:*)",
      "Bash(git clean -f:*)"
    ]
  }
}
```

# claude-harness

A reusable Claude Code configuration harness: hooks, commands, analysis scripts, and templates for a structured TDD pipeline.

## What's included

- **6-stage pipeline**: Design → Build → Analyze → Review → Critique → Ship
- **Pre/post hooks**: safety filter before Bash, gate checks after every file write
- **11 analysis scripts**: syntax, types, secrets, injection, dependencies, SAST, coverage, complexity, style, and UI consistency
- **Slash commands**: `/design`, `/build`, `/review`, `/critique`, `/ship`, `/task-status`
- **Templates**: design doc, ADR, review report, spec

## Setup

Copy the `.claude/` directory into your project root, or use it as a Claude Code plugin reference.

```bash
# Option A — copy into project
cp -r .claude /path/to/your/project/

# Option B — reference in settings.json as a plugin (Claude Code plugin format)
```

Commit `.claude/` to your project repository. The files in `.claude/state/` are runtime-only and gitignored.

See `.claude/docs/getting-started.md` for full setup instructions.

## Customising post-write gates

`hooks/post-write.sh` is pre-configured for a Python/FastAPI + Jinja project using `uv`. Adjust the path patterns and test runner for your stack. See `.claude/docs/configuration-reference.md` for all configurable environment variables.

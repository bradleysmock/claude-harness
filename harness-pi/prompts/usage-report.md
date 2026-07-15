---
description: Analyze the lead's own Claude Code usage from local ~/.claude state and write a dated usag
---
Analyze the lead's own Claude Code usage from local `~/.claude` state and write a dated usage report — patterns, an idle-excluded time estimate, strengths/weaknesses (token efficiency + output quality), and roadmap-tied recommendations.

Use the Skill tool to load and follow `usage-report`. Pass any `$ARGUMENTS` through to the analyzer (e.g. `--idle-cap 120`, `--home /path/to/.claude`).

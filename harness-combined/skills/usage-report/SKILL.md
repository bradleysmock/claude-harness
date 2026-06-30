---
name: usage-report
description: Analyze the user's own Claude Code usage across all local sessions and write a dated markdown report — usage patterns, an active-time estimate that excludes idle/away sessions, strengths/weaknesses (token efficiency + output quality), and forward-looking recommendations tied to Anthropic's public roadmap. TRIGGER when the user asks to "review my Claude Code usage", "how am I using Claude", "usage report", "where am I spending tokens/time", "how can I use Claude more efficiently", or invokes /usage-report. SKIP when the user wants the state of harness *work* (open tickets, spec/build runs — use the status skill), a code review of a diff (use review/critique), or a debug postmortem of a failed run (use debug).
---

# Usage-report skill — analyze how the lead uses Claude Code

Produce a report on the user's own Claude Code usage from local state in `~/.claude`. The numbers come from a deterministic analyzer; your job is to run it, optionally gather roadmap context, and write the prose. **Never invent metrics** — every figure must come from the analyzer JSON or a cited source.

## Step 1 — Run the analyzer

```
python3 "${CLAUDE_PLUGIN_ROOT}/skills/usage-report/analyze.py"
```

Pass through anything in `$ARGUMENTS` (e.g. `--idle-cap 120` to tighten the away-time threshold, `--home /path/to/.claude` to point at another machine's state). The script is read-only, stdlib-only, and prints one JSON document to stdout. Capture it.

Read the JSON. It has three blocks, each with its own time coverage — **keep them straight, do not blend their windows**:

- `transcripts` — full-fidelity data (tokens, time, tools, models, skills). Only spans as far back as the local cleanup job kept transcripts; treat it as the *recent intensive window*. This is the only block with a defensible time/token/cost estimate.
- `history` — every typed prompt with `first_day`/`last_day` and `prompts_by_month`. Widest coverage; use it for the growth trend and project mix.
- `stats_cache` — daily message/tool/session counts for the older window the transcripts no longer cover. Counts only, no time or tokens.

A `subagents` entry in `top_projects_by_events` is sidechain (subagent) transcript storage, not a real project — report it as delegation volume, not as a codebase.

## Step 2 — Gather roadmap context (for the recommendations section)

If web access is available, launch a subagent to fetch Anthropic's **publicly announced** Claude Code / model roadmap and published efficiency research (context engineering, writing tools for agents, prompt caching, batch API, effort control, dynamic workflows). Require primary sources (anthropic.com, code.claude.com, platform.claude.com) or reputable press, with status (shipped / announced / research) and dates. **Do not fabricate** — if a claim can't be sourced, omit it. If web access is unavailable, write the recommendations from what is verifiable and say so.

## Step 3 — Write the report

Write to `claude-usage-report-<YYYY-MM-DD>.md` in the current directory (or a path given in `$ARGUMENTS`). Use these sections:

1. **Header & coverage caveat** — the three data windows and which figures cover which span.
2. **Headline numbers** — prompts, sessions, active time, tokens, notional cost.
3. **Time spent** — active hours, and the *waiting-on-Claude vs. prompting/reading* split. State the idle cap used and that idle/away sessions were excluded. Call out what the split implies for where efficiency gains actually come from.
4. **Usage growth & where it goes** — `prompts_by_month` trend, top projects, top skills.
5. **How they drive Claude** — prompts/session, tool calls/session, sidechain (delegation) share, model mix, tool mix, cache-read share.
6. **Strengths** — grounded in the data (e.g. cache discipline, delegation, model tiering).
7. **Weaknesses & improvements** — ordered by estimated payoff; cover token efficiency (cache-write TTL, output volume, tool-error round-trips, Bash-vs-dedicated-tools, MCP tool surface) and output quality (prompt specificity, rework loops). Tie each to a number.
8. **Future recommendations** — from Step 2, framed as "Once X ships, start Y / stop Z" and "Consider trying X (research)", each with a source link and status. Flag anything announced-but-restricted as do-not-build-on-yet.
9. **Methodology & caveats** — the idle-cap rule and its sensitivity, requestId de-duplication of tokens, and that the cost is a *notional list-price* figure (a Max/Pro subscriber is not billed it). Note the pre-cleanup undercount.

## Reporting discipline

- Lead with the caveats, don't bury them. The cost is notional; the time totals shift with the idle cap; the token/time window undercounts the full period because old transcripts were pruned.
- Be specific and honest: cite the actual numbers, name the weak spots plainly, and don't pad strengths.
- Keep it skimmable — tables for numbers, short ordered lists for recommendations.

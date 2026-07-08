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

Pass through anything in `$ARGUMENTS`:
- `--idle-cap 120` — tighten the away-time threshold.
- `--home /path/to/.claude` — point at another machine's state.
- `--billing included|metered|auto` — the account's billing regime (default `auto`). `included` = subscription or enterprise seat with included usage; `metered` = API key / usage credits / usage-based contract. If the user states their plan, pass it; otherwise `auto` infers it from the data.

The script is read-only, stdlib-only, and prints one JSON document to stdout. Capture it.

Read the JSON. It has three blocks, each with its own time coverage — **keep them straight, do not blend their windows**:

- `transcripts` — full-fidelity data (tokens, time, tools, models, skills). Only spans as far back as the local cleanup job kept transcripts; treat it as the *recent intensive window*. This is the only block with a defensible time/token/cost estimate.
- `history` — every typed prompt with `first_day`/`last_day` and `prompts_by_month`. Widest coverage; use it for the growth trend and project mix.
- `stats_cache` — daily message/tool/session counts for the older window the transcripts no longer cover. Counts only, no time or tokens.

After reading the JSON, cross-reference `history.top_projects_by_prompts` against `transcripts.top_projects_by_events`. Any project that accounts for > 5% of total history prompts but is absent from the transcripts must be explicitly named in every section that draws on tool-use, model-mix, error-rate, or cost data. Do not present those findings as general behavioral conclusions — qualify them as "transcripts window only, excluding [project]."

A `subagents` entry in `top_projects_by_events` is sidechain (subagent) transcript storage, not a real project — report it as delegation volume, not as a codebase.

**Billing regime drives the cache recommendation — read it before writing section 7.** In `transcripts`:
- `billing_mode` (`included` / `metered` / `mixed` / `unknown`) and `billing_basis` (how it was determined).
- `cost_is_billed` — when `false`, the `notional_cost_usd` is a comparative figure only, **not** a bill.
- `cache_write_ttl` — the observed 1h-vs-5m write split, broken out by `main_thread`, `subagents`, and `by_project`. **Subagents use a 5m cache by Claude Code's internal default regardless of billing — never read subagent 5m as a metered-account signal.** Only `main_thread` TTL reflects the account's billing. A `by_project` split with both 1h and 5m main-thread projects can indicate more than one account (e.g. a personal subscription and a work enterprise account).

## Step 2 — Gather roadmap context (for the recommendations section)

If web access is available, launch a subagent to fetch Anthropic's **publicly announced** Claude Code / model roadmap and published efficiency research (context engineering, writing tools for agents, prompt caching, batch API, effort control, dynamic workflows). Require primary sources (anthropic.com, code.claude.com, platform.claude.com) or reputable press, with status (shipped / announced / research) and dates. **Do not fabricate** — if a claim can't be sourced, omit it. If web access is unavailable, write the recommendations from what is verifiable and say so.

## Step 3 — Write the report

Write to `claude-usage-report-<YYYY-MM-DD>.md` in the current directory (or a path given in `$ARGUMENTS`). Use these sections:

1. **Header & coverage caveat** — the three data windows and which figures cover which span.
2. **Headline numbers** — prompts, sessions, active time, tokens, notional cost.
3. **Time spent** — active hours, and the *waiting-on-Claude vs. prompting/reading* split. State the idle cap used and that idle/away sessions were excluded. If `time_sensitivity_active_hours` is present in the data, report active time as a range (e.g. "58–101 h depending on idle definition") rather than a single figure. Qualify any I/O-bound claim with that range — do not assert a specific percentage as if it were precise.
4. **Usage growth & where it goes** — `prompts_by_month` trend, top projects, top skills. Before drawing a month-over-month intensity trend from `monthly_tokens`, cross-check which projects were active in each month (from `top_projects_by_events`). If the project mix changed, note that the token difference may reflect project composition rather than a behavioral shift in how much work each prompt drives.
5. **How they drive Claude** — prompts/session, tool calls/session, sidechain (delegation) share, model mix, tool mix, cache-read share.
6. **Strengths** — grounded in the data (e.g. delegation, model tiering). Two specific guards:
   - *Cache-read share* is partly structural — system prompts, tool definitions, and CLAUDE.md are cached by the runtime by default. Only flag it as a user strength if there is specific evidence of active session continuity keeping it high. Flag it as a concern only if it drops below ~80%. Do not list a high cache-read rate as a behavioral strength with no actionable advice attached.
   - *Model tiering* — evaluate against cost distribution, not just turn distribution. If the highest-tier model accounts for > 50% of notional cost despite tiering, describe it as "tiering present but [model] still dominates cost — not yet sufficient" rather than listing it as a strength.
7. **Weaknesses & improvements** — ordered by estimated payoff; cover token efficiency (output volume, tool-error round-trips, Bash-vs-dedicated-tools, MCP tool surface) and output quality (prompt specificity, rework loops). Tie each to a number. Only attribute tool-error rates to a specific tool if `tool_errors_by_tool` is present and shows a meaningful concentration in that tool; without a per-tool breakdown, report the aggregate rate and state that root cause is unattributed — do not infer cause from tool call volume alone. The **cache-write TTL** item is billing-sensitive — apply the matrix below, do not give a blanket "switch to 5m":
   - **`included`** (subscription / enterprise seat): 1h is the *correct* default — it costs nothing extra on the plan and widens the warm-cache window. Do **not** recommend forcing 5m; it would only shrink the warm window and add recompute latency (which matters given the waiting-on-Claude share). Frame cache work as *preservation for latency*: keep model+effort constant per session, run `/compact` at task boundaries not mid-task, load MCP servers up front, prefer `/rewind`. The notional cost is not billed — say so.
   - **`metered`** (API / credits / usage-based): cache-write TTL is real money. Flag main-thread 1h writes on bursty (<5-min-gap) sessions as overspend, and quantify the saving from the observed `main_thread` 1h volume at 2× vs 1.25× input. Recommend `FORCE_PROMPT_CACHING_5M=1` for interactive work, reserving 1h (`ENABLE_PROMPT_CACHING_1H=1`) for genuinely long-gap workflows.
   - **`mixed` / `unknown`**: state the assumption, show the per-account split if present, and recommend re-running with `--billing` set. Never assert a dollar saving you can't tie to a metered account.
8. **Future recommendations** — from Step 2, framed as "Once X ships, start Y / stop Z" and "Consider trying X (research)", each with a source link and status. Flag anything announced-but-restricted as do-not-build-on-yet. Three additional guards:
   - *`effort` parameter*: estimate the expected output-token reduction by citing Anthropic's published benchmarks, or state explicitly that the saving is unquantified. If the user runs a large custom plugin surface that would need retrofitting, note the implementation complexity — do not treat it as a simple config change.
   - *Beta features*: only recommend them for non-critical or experimental workflows. Do not recommend wiring a beta feature into core production automation (e.g. primary autopilot or sprint workflows).
   - *Batch API*: before recommending it for a named workflow, reason about whether that workflow has sequential data dependencies that would prevent async batching, and note if it is on the critical path of an interactive session (where async latency trades cost savings for productivity).
9. **Methodology & caveats** — the idle-cap rule and its sensitivity, requestId de-duplication of tokens, how `billing_mode` was determined (`billing_basis`), and that the cost is a *notional list-price* figure that is only billed on a `metered` account (an `included` subscription/enterprise seat is not billed it). Note the pre-cleanup undercount.

## Reporting discipline

- Lead with the caveats, don't bury them. The cost is notional; the time totals shift with the idle cap; the token/time window undercounts the full period because old transcripts were pruned.
- Be specific and honest: cite the actual numbers, name the weak spots plainly, and don't pad strengths.
- Keep it skimmable — tables for numbers, short ordered lists for recommendations.

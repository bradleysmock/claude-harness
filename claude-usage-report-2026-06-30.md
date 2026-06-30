# Claude Code Usage Report — Bradley

**Window analyzed:** 2026-01-13 → 2026-06-30 (~5.5 months)
**Generated:** 2026-06-30
**Sources:** 715 session transcripts (`~/.claude/projects/`), `history.jsonl` (1,979 typed prompts), `stats-cache.json` (daily aggregates)

> **Data-coverage caveat.** Full-fidelity transcripts (tokens, timestamps, tool calls) only survive from **2026-05-16 onward** — older sessions were pruned by the cleanup job. So this report uses three lenses:
> - **Prompt history** (`history.jsonl`) — complete, Jan 13 → Jun 30.
> - **Daily aggregates** (`stats-cache.json`) — Jan 13 → May 17 (message/tool/session counts only).
> - **Detailed transcripts** — May 16 → Jun 30 (tokens, time, tools, models). All token/time/cost figures below are for this ~6-week window unless stated.

---

## 1. Headline numbers

| Metric | Value | Scope |
|---|---|---|
| Typed prompts | **1,979** | full period |
| Active days | 24 (Jan–mid May) + 35 (mid May–Jun) | both windows |
| Sessions | 87 + 178 | both windows |
| Active time (excl. idle) | **136.3 h** | May 16–Jun 30 |
| — waiting on Claude | **120.0 h (88%)** | May 16–Jun 30 |
| — your prompting/reading | **16.3 h (12%)** | May 16–Jun 30 |
| Idle time excluded | 2,265 h | sessions left open |
| Output tokens (real work) | **18.3 M** | May 16–Jun 30 |
| Cache-read tokens | **2.66 B** | May 16–Jun 30 |
| Notional API-equivalent cost | **≈ $2,200** *(not billed — included plan)* | May 16–Jun 30 |

---

## 2. Time spent (the part you asked to scope carefully)

I reconstructed active time per session by summing the gaps between consecutive events and **discarding any gap longer than 5 minutes** as "away" time. This is what cleanly separates real work from the 2,265 hours of sessions you left open in the background.

For the **May 16 – Jun 30** window (the only window with timestamps):

- **Total active time: ~136 hours** across 35 active days → **~3.9 h/day** on days you worked.
- **~120 h (88%) was you waiting on Claude** (model generation + tool execution).
- **~16 h (12%) was you reading output and typing** the next prompt.
- Busiest days: **May 23 (12.7 h)**, Jun 24 (11.4 h), Jun 20 (10.6 h) — multi-session marathon days.

The 88/12 split is the single most important number in this report: **your throughput is bounded almost entirely by Claude's wall-clock time, not your typing.** That reframes "efficiency" — saving keystrokes barely matters; cutting wasted model/tool round-trips and using faster inference matters a lot (see §6).

> Earlier window (Jan 13–May 17), where only counts survive: **30,070 messages, 15,661 tool calls, 87 sessions** over 24 active days. No reliable time estimate is possible there, but the per-session message/tool density is consistent with the May–June numbers.

---

## 3. Usage growth & where it goes

**Prompts per month** (full history) show a steep ramp — this went from occasional to daily-driver:

```
Jan   44
Feb    3
Mar  112
Apr  340
May  632
Jun  848
```

**Top projects by typed prompts** (full period):

| Project | Prompts |
|---|---|
| exploration/claude-dev | 626 |
| flock-and-fiber | 190 |
| exploration/claude-harness/sample-app2 | 175 |
| fowl-feather | 148 |
| exploration/claude-harness/sample-app | 148 |
| membership2 | 125 |
| claude-harness | 91 |

The bulk of effort is **building and dogfooding your own agentic harness** (`claude-harness`, the `harness*` plugins, the sample apps) plus two real products (`flock-and-fiber`, `fowl-feather`, `membership2`).

**Most-used skills** (by attribution, May–Jun): `autopilot` (11.7k), `build` (8.7k), `problem` (6.2k), `dispatching-parallel-agents` (3.8k), `task` (3.7k). You run a **spec → build → deliver pipeline with heavy parallel-subagent orchestration**, not ad-hoc chatting.

---

## 4. How you drive Claude

| Signal | Value | Read |
|---|---|---|
| Median prompts/session | **6** | short conversational steering… |
| Median tool calls/session | **148** | …driving very heavy autonomous work |
| Sidechain (subagent) turns | **18,123** (vs 40,727 main) | ~31% of all model turns are delegated |
| Median prompt length | **130 chars** | terse instructions |
| Mean / p90 / max prompt | 1,041 / 772 / 19,430 chars | bimodal: short steers + occasional big pastes |
| Prompts with pasted blobs | 52 | |

**Tool mix** (main thread, May–Jun):

```
Bash    8,536   ███████████████████  (38% of main tool calls)
Read    4,471   ██████████
Edit    3,974   █████████
Write   2,147   █████
Agent     475
gate_run  426
ToolSearch 337
```

**Model mix** (by API turn): Sonnet 4.6 **65.8%**, Opus 4.8 **32.1%**, Opus 4.7 1.3%, Haiku 4.5 0.6%. Sonnet does the bulk (largely subagents); Opus carries lead reasoning.

**Token shape:** cache reads are **96.3% of all input-side tokens** — extremely cache-efficient. Output (18.3 M) and cache *writes* (99.4 M) dominate the *notional* cost, not fresh input — but on your included plan that cost isn't billed (see §6.1). Cache writes split **100% 1h on the main thread / 5m on subagents**, which is exactly what Claude Code does on included-usage auth.

---

## 5. Strengths

1. **Outstanding cache discipline.** 96.3% of input is cache reads (billed at 0.1×). Most users leak money on cold context; you don't. This is the biggest lever in token economics and you're already pulling it.
2. **You delegate aggressively and correctly.** ~31% of model turns are subagents, and you tier models well — Sonnet for bulk/parallel work, Opus for hard lead reasoning, Haiku for cheap tasks. That's textbook cost-aware orchestration.
3. **High autonomy per steer.** 148 tool calls against 6 prompts per session means you let Claude *run*, rather than babysitting one edit at a time. This is where agentic tools pay off.
4. **Structured, repeatable workflow.** Spec → build → gate → deliver with checkpoints and critic passes. This produces reviewable, restartable work and is why your sessions sustain 10+ active hours.
5. **Idle sessions cost nothing.** The 2,265 h of open-but-idle sessions don't burn tokens — leaving terminals open is harmless housekeeping, not waste.

## 6. Weaknesses & concrete improvements

Ordered by estimated payoff. Remember the 88% finding: **optimize round-trips and latency, not keystrokes.**

1. **Cache-write TTL — billing-sensitive, and on your plan it's a latency lever, not a cost lever.** Your **main-thread** cache writes are **100% 1-hour TTL**; the 5-minute writes in the data are **all from subagents** (Claude Code uses a 5m cache for subagents by default, regardless of billing). Claude Code auto-selects 1h main-thread caching for **included-usage auth** (a subscription or an enterprise seat with included usage) — which is what these sessions ran on. On that billing, **1h is correct**: it costs nothing extra and widens the warm-cache window, which *reduces* the recompute that drives your 120 h of waiting. So the ~$770 notional cache-write figure is **not a bill**, and forcing 5m would be strictly worse here. *Action (included plan): leave TTL at 1h; treat cache as a latency lever — keep model+effort constant per session, run `/compact` at task boundaries not mid-task, load MCP servers up front, prefer `/rewind`.* *Action (only if you also run work on a **metered** API/usage-based account): on that account, set `FORCE_PROMPT_CACHING_5M=1` for short interactive sessions and reserve `ENABLE_PROMPT_CACHING_1H=1` for genuinely long-gap workflows — there the 2× vs 1.25× write cost is real money.*

2. **Output tokens (18.3 M) dominate real spend** and, more importantly, **drive the 120 h of waiting** — long generations are slow generations. *Action: use the **effort control** on Opus 4.8 (standard / extra / `xhigh`). Reserve `xhigh`/max for design and hard debugging; run routine `build`/`gate`/`deliver` at standard effort. Expect both lower cost and less waiting.*

3. **3.5% tool-error rate (1,215 failed tool calls).** Every failure is a wasted round-trip — tokens *and* latency, the thing that actually bounds you. Likely culprits: `Edit` string-match misses and `Bash` path/permission issues. *Action: spend 30 min auditing the top recurring tool errors; even halving them removes ~600 dead round-trips/quarter.*

4. **Bash is 38% of tool calls (8,536).** Some fraction is almost certainly `cat`/`sed`/`echo`/`grep` that the dedicated `Read`/`Grep`/`Glob` tools do more cheaply, more cache-friendly, and without permission prompts. *Action: lean on dedicated tools; they keep context stable (better cache hits) and avoid the permission round-trips that add latency.*

5. **Large MCP/tool surface.** You load many MCP servers (harness, harness-combined, superpowers, Google Drive/Gmail/Calendar, Sentry, Indeed…). Anthropic measures ~55K tokens of overhead for ~58 tools *before the conversation starts*. You already use `ToolSearch` (337×) — good — but servers you never call (e.g., Indeed, Gmail) still tax every session. *Action: trim default-loaded MCP servers to the ones you actually use; keep the rest behind deferred/Tool-Search loading.*

6. **Prompt style is bimodal (130-char steers + 19K pastes).** With your harness scaffolding the short steers mostly work, but the occasional huge paste + terse instruction is where rework loops start. *Action: for net-new/ambiguous tasks, front-load acceptance criteria and constraints in the *first* prompt rather than correcting mid-run — corrections are the most expensive tokens because they invalidate cache and re-run tool chains.*

---

## 7. Future-usage recommendations (Anthropic's public roadmap & research)

Sourced from Anthropic primary pages and reputable press as of 2026-06-30. Verify availability before acting on the gated/restricted items.

### "Once X ships, start Y / stop Z"

- **Once *dynamic workflows* reaches your plan tier** (research preview, announced May 28 2026 with Opus 4.8; Enterprise/Team/Max) → **start** using it for codebase-scale refactors/migrations (it plans, fans out to tens–hundreds of self-checking parallel subagents in one session) and **stop** hand-rolling parallel dispatch via `superpowers:dispatching-parallel-agents` (your 3,758 attributions). It's the native version of exactly what you're already simulating.
  Sources: [claude.com/blog/introducing-dynamic-workflows-in-claude-code](https://claude.com/blog/introducing-dynamic-workflows-in-claude-code), [code.claude.com/docs/en/workflows](https://code.claude.com/docs/en/workflows)

- **Opus 4.8 effort control is already shipped** → **start** routing routine pipeline stages (`build`, `gate`, `deliver`) at standard effort and reserve `xhigh` for `problem`/design. Directly attacks weaknesses #2 and your 120 h wait. Source: [anthropic.com/news/claude-opus-4-8](https://www.anthropic.com/news/claude-opus-4-8)

- **Opus 4.8 Fast mode is shipped** ($10/$50 at ~2.5× speed, ~3× cheaper than prior fast modes) → for latency-sensitive interactive sessions, **start** toggling Fast mode (`/fast`). Since 88% of your active time is waiting, throughput-per-dollar here is unusually favorable for your usage. Source: [anthropic.com/news/claude-opus-4-8](https://www.anthropic.com/news/claude-opus-4-8)

- **Batch API is shipped (50% off, async, ≤24 h)** → your `autopilot` runs (11.7k attributions) are largely non-interactive. **Start** routing overnight/unattended autopilot through the Batch API where the harness allows; it stacks with caching. Source: [finout.io/blog/anthropic-api-pricing](https://www.finout.io/blog/anthropic-api-pricing)

- **Stop** carrying aggressive `CRITICAL: YOU MUST` tool-prompt language from older models — current Opus follows instructions more literally and over-triggers. Relevant to your harness skill/tool prompts. Source: [anthropic.com/news/claude-opus-4-8](https://www.anthropic.com/news/claude-opus-4-8)

### "Consider trying X (currently research / recently published)"

- **Tool Search Tool + Code Execution with MCP** — measured ~85% context reduction on large tool sets and accuracy gains. Directly addresses weakness #5; you've already adopted `ToolSearch`, so lean further in and move rarely-used MCP servers behind it. Sources: [anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use), [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **"Effective context engineering for AI agents"** (Sep 29 2025) — just-in-time retrieval via lightweight identifiers and compaction (recall-first, then precision). Your harness already does spec/context fetch; this is the canonical framework to formalize it. Source: [anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

- **"Writing effective tools for AI agents"** (Sep 11 2025) — tool consolidation, concise `ResponseFormat` enums (206→72 tokens for the same info), pagination/truncation defaults; Claude Code caps tool responses at 25K tokens. Worth a pass over your custom harness MCP tools to trim response verbosity. Source: [anthropic.com/engineering/writing-tools-for-agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

- **Mid-task system-prompt update without breaking the cache** (Opus 4.8) — you can revise instructions mid-run via Messages-API system entries while preserving prompt cache. Directly useful for your build/repair loops where the harness adjusts guidance mid-task. Source: [anthropic.com/news/claude-opus-4-8](https://www.anthropic.com/news/claude-opus-4-8)

### Watch / do not build on yet

- **Fable 5 / Mythos 5** (top tier) were released June 9 2026 but **access was suspended June 12 2026** under a reported US export-control directive. Treat as *announced but currently restricted* — do not design workflows that assume you can call them today; re-verify before relying on them. Sources: [anthropic.com/news/claude-fable-5-mythos-5](https://www.anthropic.com/news/claude-fable-5-mythos-5), [cnbc.com/2026/06/09/anthropic-mythos-claude-fable-5.html](https://www.cnbc.com/2026/06/09/anthropic-mythos-claude-fable-5.html)

---

## 8. Methodology & caveats

- **Active time** = sum of inter-event gaps per session, with any gap > 300 s dropped as idle. Sensitive to that threshold; a 120 s cap would lower totals ~10–15%, a 600 s cap would raise them similarly.
- **Waiting vs. prompting** split: a gap ending in an assistant/tool event counts as "waiting on Claude"; a gap ending in a typed prompt counts as "prompting/reading."
- **Tokens** are de-duplicated by `requestId` to avoid counting streamed content blocks multiple times.
- **Cost (~$2,200)** is a *notional API-equivalent* at public list prices, computed from the **actual** cache-write TTL split in your transcripts (1h writes at 2× input, 5m at 1.25×). Your account runs on **included-usage billing** (subscription / enterprise seat — inferred from 100% 1h main-thread caching), so you are **not** billed this; it's a comparative figure for sizing efficiency wins. It would only be a real bill on a metered API / usage-based account.
- Pre-May-16 transcripts are pruned, so token/time figures **undercount the full 5.5-month period** — they cover the most intense ~6 weeks only.
```

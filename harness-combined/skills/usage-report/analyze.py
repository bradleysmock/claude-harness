#!/usr/bin/env python3
"""Deterministic Claude Code usage analyzer.

Scans the local Claude Code state (`~/.claude`) and emits a single JSON
document of usage metrics on stdout. It does no synthesis and makes no
network calls — the `usage-report` skill turns this JSON into the prose
report. Stdlib only, read-only.

Sources, with their coverage caveats:
  - projects/**/*.jsonl  full-fidelity transcripts (tokens, timestamps,
                         tools, models) — only as far back as cleanup kept
  - history.jsonl        every typed prompt (widest time coverage)
  - stats-cache.json     daily message/tool/session counts for the older
                         window the transcripts no longer cover
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import statistics

# Notional list prices, USD per 1M tokens: (input, output, cache_read).
# Cache-write prices are derived from the input price by TTL multiplier
# (see below), since a 1h write costs 2x input and a 5m write 1.25x. This
# estimate is only billed on metered (API/credits/usage-based) accounts; a
# subscription or included-usage enterprise seat is not billed it.
PRICES = {
    "claude-opus-4-8": (5.0, 25.0, 0.5),
    "claude-opus-4-7": (5.0, 25.0, 0.5),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.1),
}
DEFAULT_PRICE = (5.0, 25.0, 0.5)
# Cache-write cost as a multiple of the input price, by ephemeral TTL.
WRITE_MULT_1H = 2.0
WRITE_MULT_5M = 1.25
# Auth method drives Claude Code's default cache TTL: subscription -> 1h
# (included usage, free upside), metered/API -> 5m (cheaper writes). So the
# observed TTL split is itself a signal of the billing regime in play.
BILLING_METERED = "metered"
BILLING_INCLUDED = "included"


def parse_ts(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def month_of(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m")


def day_of(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d")


# Project transcript dirs are the cwd path with separators turned into
# dashes, e.g. "-Users-alice-workspaces-myapp". Strip the encoded home (and
# an optional "workspaces" segment) so the label is just the project name.
_ENCODED_HOME = re.compile(r"^-(?:Users|home)-[^-]+-(?:workspaces-)?")


def clean_project(name):
    return _ENCODED_HOME.sub("", name)


def is_tool_result(content):
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


class Accumulator:
    """Mutable bag of counters threaded through the transcript scan."""

    def __init__(self, idle_cap):
        self.idle_cap = idle_cap
        self.tok = collections.defaultdict(lambda: collections.defaultdict(int))
        self.cache_ttl_by_project = collections.defaultdict(
            lambda: collections.defaultdict(int)
        )
        self.cache_ttl_scope = {
            "main": collections.defaultdict(int),
            "side": collections.defaultdict(int),
        }
        self.month_tok = collections.defaultdict(lambda: collections.defaultdict(int))
        self.model_turns = collections.Counter()
        self.tools_main = collections.Counter()
        self.skills = collections.Counter()
        self.plugins = collections.Counter()
        self.project_events = collections.Counter()
        self.seen_requests = set()
        self.prompt_lens = []
        self.day_active = collections.defaultdict(float)
        self.session_ids = set()
        self.tools_per_session = collections.defaultdict(int)
        self.prompts_per_session = collections.defaultdict(int)
        self.sidechain_turns = 0
        self.main_turns = 0
        self.human_prompts = 0
        self.tool_results = 0
        self.tool_errors = 0
        self.tool_id_to_name = {}
        self.tool_errors_by_tool = collections.Counter()
        self.claude_time = 0.0
        self.human_time = 0.0
        self.active_time = 0.0
        self.idle_excluded = 0.0
        self.sessions = collections.defaultdict(list)

    def record_usage(self, model, usage, epoch, project, side):
        breakdown = usage.get("cache_creation") or {}
        write_1h = breakdown.get("ephemeral_1h_input_tokens", 0)
        write_5m = breakdown.get("ephemeral_5m_input_tokens", 0)
        fields = (
            ("input", usage.get("input_tokens", 0)),
            ("output", usage.get("output_tokens", 0)),
            ("cache_creation", usage.get("cache_creation_input_tokens", 0)),
            ("cache_read", usage.get("cache_read_input_tokens", 0)),
            ("cache_write_1h", write_1h),
            ("cache_write_5m", write_5m),
        )
        for key, value in fields:
            self.tok[model][key] += value
        self.cache_ttl_by_project[project]["1h"] += write_1h
        self.cache_ttl_by_project[project]["5m"] += write_5m
        # Subagents use a 5m cache by Claude Code's internal default
        # regardless of billing, so only main-thread writes signal the
        # account's billing regime.
        scope = "side" if side else "main"
        self.cache_ttl_scope[scope]["1h"] += write_1h
        self.cache_ttl_scope[scope]["5m"] += write_5m
        self.model_turns[model] += 1
        if epoch is None:
            return
        bucket = month_of(epoch)
        for key, value in fields:
            self.month_tok[bucket][key] += value


def scan_assistant(record, acc, project):
    msg = record.get("message", {})
    model = msg.get("model", "unknown")
    request_id = record.get("requestId")
    usage = msg.get("usage", {})
    epoch = parse_ts(record.get("timestamp"))
    sid = record.get("sessionId")
    side = bool(record.get("isSidechain"))
    if request_id and request_id not in acc.seen_requests and usage:
        acc.seen_requests.add(request_id)
        acc.record_usage(model, usage, epoch, project, side)
    if side:
        acc.sidechain_turns += 1
    else:
        acc.main_turns += 1
    content = msg.get("content")
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            if not side:
                acc.tools_main[block.get("name", "?")] += 1
            if sid:
                acc.tools_per_session[sid] += 1
            tool_id = block.get("id")
            if tool_id:
                acc.tool_id_to_name[tool_id] = block.get("name", "?")
    skill = record.get("attributionSkill")
    plugin = record.get("attributionPlugin")
    if skill:
        acc.skills[skill] += 1
    if plugin:
        acc.plugins[plugin] += 1
    if epoch and sid:
        acc.sessions[sid].append((epoch, "assistant"))


def scan_user(record, acc):
    msg = record.get("message", {})
    content = msg.get("content")
    epoch = parse_ts(record.get("timestamp"))
    sid = record.get("sessionId")
    side = bool(record.get("isSidechain"))
    if is_tool_result(content):
        acc.tool_results += 1
        for block in content:
            if isinstance(block, dict) and block.get("is_error"):
                acc.tool_errors += 1
                tool_name = acc.tool_id_to_name.get(block.get("tool_use_id"), "unknown")
                acc.tool_errors_by_tool[tool_name] += 1
        if epoch and sid:
            acc.sessions[sid].append((epoch, "tool_result"))
    elif isinstance(content, str) and not record.get("isMeta") and not side:
        acc.human_prompts += 1
        acc.prompt_lens.append(len(content))
        if sid:
            acc.prompts_per_session[sid] += 1
        if epoch and sid:
            acc.sessions[sid].append((epoch, "human"))
    elif epoch and sid:
        acc.sessions[sid].append((epoch, "other"))


def scan_transcripts(projects_root, acc):
    pattern = os.path.join(projects_root, "**", "*.jsonl")
    for path in glob.glob(pattern, recursive=True):
        try:
            handle = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        project = os.path.basename(os.path.dirname(path))
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = record.get("sessionId")
                if sid:
                    acc.session_ids.add(sid)
                if parse_ts(record.get("timestamp")) and sid:
                    acc.project_events[project] += 1
                kind = record.get("type")
                if kind == "assistant":
                    scan_assistant(record, acc, project)
                elif kind == "user":
                    scan_user(record, acc)
                elif kind == "system" and sid:
                    epoch = parse_ts(record.get("timestamp"))
                    if epoch:
                        acc.sessions[sid].append((epoch, "system"))


def _time_for_cap(sessions, idle_cap):
    active_time = 0.0
    claude_time = 0.0
    human_time = 0.0
    idle_excluded = 0.0
    day_active = collections.defaultdict(float)
    for events in sessions.values():
        events.sort(key=lambda item: item[0])
        for index in range(1, len(events)):
            gap = events[index][0] - events[index - 1][0]
            if gap <= 0:
                continue
            if gap > idle_cap:
                idle_excluded += gap
                continue
            active_time += gap
            day_active[day_of(events[index][0])] += gap
            if events[index][1] == "human":
                human_time += gap
            else:
                claude_time += gap
    return active_time, claude_time, human_time, idle_excluded, day_active


def compute_time(acc):
    result = _time_for_cap(acc.sessions, acc.idle_cap)
    acc.active_time, acc.claude_time, acc.human_time, acc.idle_excluded, acc.day_active = result


def write_cost(counts, p_in):
    """Cache-write cost using the actual 1h/5m TTL split when present,
    falling back to all-1h for older records that lack the breakdown."""
    write_1h = counts.get("cache_write_1h", 0)
    write_5m = counts.get("cache_write_5m", 0)
    classified = write_1h + write_5m
    unclassified = counts.get("cache_creation", 0) - classified
    if unclassified < 0:
        unclassified = 0
    return p_in * (
        write_1h * WRITE_MULT_1H
        + write_5m * WRITE_MULT_5M
        + unclassified * WRITE_MULT_1H
    )


def estimate_cost(tok):
    total = 0.0
    by_model = {}
    for model, counts in tok.items():
        p_in, p_out, p_read = PRICES.get(model, DEFAULT_PRICE)
        cost = (
            counts.get("input", 0) * p_in
            + counts.get("output", 0) * p_out
            + counts.get("cache_read", 0) * p_read
            + write_cost(counts, p_in)
        ) / 1_000_000
        if cost:
            by_model[model] = round(cost, 2)
        total += cost
    return round(total, 2), by_model


def infer_billing(billing_arg, main_1h, main_5m):
    """Resolve the billing regime from MAIN-THREAD cache writes (subagents
    use 5m regardless of billing, so they're excluded). An explicit flag
    wins; otherwise infer, since Claude Code picks 1h for subscription auth
    and 5m for metered/API auth."""
    if billing_arg in (BILLING_METERED, BILLING_INCLUDED):
        return billing_arg, "explicit (--billing)"
    total = main_1h + main_5m
    if total == 0:
        return "unknown", "no main-thread cache writes observed"
    share_1h = main_1h / total
    if share_1h >= 0.6:
        return BILLING_INCLUDED, (
            f"inferred from {share_1h:.0%} 1h main-thread cache writes"
        )
    if share_1h <= 0.4:
        return BILLING_METERED, (
            f"inferred from {1 - share_1h:.0%} 5m main-thread cache writes"
        )
    return "mixed", (
        f"mixed main-thread TTL ({share_1h:.0%} 1h) — possibly >1 account"
    )


def read_history(home):
    path = os.path.join(home, "history.jsonl")
    months = collections.Counter()
    projects = collections.Counter()
    total = 0
    earliest = None
    latest = None
    try:
        handle = open(path, "r", encoding="utf-8")
    except OSError:
        return None
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            stamp = record.get("timestamp")
            if not isinstance(stamp, (int, float)):
                continue
            epoch = stamp / 1000
            total += 1
            months[month_of(epoch)] += 1
            proj = record.get("project", "")
            home = os.path.expanduser("~")
            short = proj
            if short.startswith(home):
                short = short[len(home):].lstrip("/")
            short = re.sub(r"^workspaces/", "", short)
            projects[short or "(unknown)"] += 1
            earliest = epoch if earliest is None else min(earliest, epoch)
            latest = epoch if latest is None else max(latest, epoch)
    return {
        "total_prompts": total,
        "first_day": day_of(earliest) if earliest else None,
        "last_day": day_of(latest) if latest else None,
        "prompts_by_month": dict(sorted(months.items())),
        "top_projects_by_prompts": dict(projects.most_common(15)),
    }


def read_stats_cache(home):
    path = os.path.join(home, "stats-cache.json")
    try:
        handle = open(path, "r", encoding="utf-8")
    except OSError:
        return None
    with handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError:
            return None
    days = data.get("dailyActivity", [])
    if not days:
        return None
    return {
        "last_computed": data.get("lastComputedDate"),
        "active_days": len(days),
        "first_day": days[0].get("date"),
        "last_day": days[-1].get("date"),
        "total_messages": sum(d.get("messageCount", 0) for d in days),
        "total_tool_calls": sum(d.get("toolCallCount", 0) for d in days),
        "total_sessions": sum(d.get("sessionCount", 0) for d in days),
    }


def build_cache_ttl(acc, totals):
    """Observed cache-write TTL split (overall + per project) and the
    resulting billing-regime read. Per-project lets a personal subscription
    (1h) be told apart from a metered work account (5m)."""
    write_1h = totals["cache_write_1h"]
    write_5m = totals["cache_write_5m"]
    classified = write_1h + write_5m
    pct_1h = round(100 * write_1h / classified, 1) if classified else None
    per_project = {}
    for project, split in acc.cache_ttl_by_project.items():
        sub_total = split["1h"] + split["5m"]
        if sub_total == 0:
            continue
        per_project[clean_project(project)] = {
            "ephemeral_1h": split["1h"],
            "ephemeral_5m": split["5m"],
            "pct_1h": round(100 * split["1h"] / sub_total, 1),
        }
    ranked = sorted(
        per_project.items(),
        key=lambda kv: -(kv[1]["ephemeral_1h"] + kv[1]["ephemeral_5m"]),
    )
    main = acc.cache_ttl_scope["main"]
    side = acc.cache_ttl_scope["side"]
    main_total = main["1h"] + main["5m"]
    return {
        "ephemeral_1h": write_1h,
        "ephemeral_5m": write_5m,
        "pct_1h": pct_1h,
        "main_thread": {
            "ephemeral_1h": main["1h"],
            "ephemeral_5m": main["5m"],
            "pct_1h": round(100 * main["1h"] / main_total, 1) if main_total else None,
        },
        "subagents": {
            "ephemeral_1h": side["1h"],
            "ephemeral_5m": side["5m"],
        },
        "by_project": dict(ranked[:15]),
    }


def build_report(acc, home, billing_arg):
    def hours(seconds):
        return round(seconds / 3600, 1)

    totals = collections.Counter()
    for counts in acc.tok.values():
        for key, value in counts.items():
            totals[key] += value
    input_side = totals["input"] + totals["cache_creation"] + totals["cache_read"]
    cache_pct = round(100 * totals["cache_read"] / input_side, 1) if input_side else 0
    cost_total, cost_by_model = estimate_cost(acc.tok)
    ttl = build_cache_ttl(acc, totals)
    main_scope = acc.cache_ttl_scope["main"]
    billing_mode, billing_basis = infer_billing(
        billing_arg, main_scope["1h"], main_scope["5m"]
    )
    prompt_stats = {}
    if acc.prompt_lens:
        ordered = sorted(acc.prompt_lens)
        prompt_stats = {
            "count": len(ordered),
            "median": int(statistics.median(ordered)),
            "mean": int(statistics.mean(ordered)),
            "p90": int(ordered[int(0.9 * len(ordered))]),
            "max": max(ordered),
        }
    tool_uses = list(acc.tools_per_session.values())
    prompts = list(acc.prompts_per_session.values())
    busiest = sorted(acc.day_active.items(), key=lambda item: -item[1])[:12]
    sensitivity_active_hours = {
        f"{cap}s": round(_time_for_cap(acc.sessions, cap)[0] / 3600, 1)
        for cap in (120, 300, 600)
    }
    return {
        "generated": day_of(dt.datetime.now(dt.timezone.utc).timestamp()),
        "transcripts": {
            "sessions": len(acc.session_ids),
            "human_prompts": acc.human_prompts,
            "main_assistant_turns": acc.main_turns,
            "sidechain_assistant_turns": acc.sidechain_turns,
            "deduped_api_turns": sum(acc.model_turns.values()),
            "active_days": len(acc.day_active),
            "time_hours": {
                "active": hours(acc.active_time),
                "waiting_on_claude": hours(acc.claude_time),
                "prompting_reading": hours(acc.human_time),
                "excluded_idle": hours(acc.idle_excluded),
                "idle_cap_seconds": acc.idle_cap,
            },
            "time_sensitivity_active_hours": sensitivity_active_hours,
            "model_turns": dict(acc.model_turns.most_common()),
            "tokens_total": dict(totals),
            "tokens_by_model": {m: dict(c) for m, c in acc.tok.items()},
            "cache_read_pct_of_input": cache_pct,
            "billing_mode": billing_mode,
            "billing_basis": billing_basis,
            "cost_is_billed": billing_mode == BILLING_METERED,
            "notional_cost_usd": cost_total,
            "notional_cost_by_model": cost_by_model,
            "cache_write_ttl": ttl,
            "top_tools_main": dict(acc.tools_main.most_common(20)),
            "top_skills": dict(acc.skills.most_common(15)),
            "top_plugins": dict(acc.plugins.most_common(10)),
            "tool_results": acc.tool_results,
            "tool_errors": acc.tool_errors,
            "tool_errors_by_tool": dict(acc.tool_errors_by_tool.most_common()),
            "tool_error_rate_pct": (
                round(100 * acc.tool_errors / acc.tool_results, 1)
                if acc.tool_results
                else 0
            ),
            "prompt_len_chars": prompt_stats,
            "per_session": {
                "median_tool_uses": int(statistics.median(tool_uses)) if tool_uses else 0,
                "mean_tool_uses": round(statistics.mean(tool_uses), 1) if tool_uses else 0,
                "median_prompts": int(statistics.median(prompts)) if prompts else 0,
                "mean_prompts": round(statistics.mean(prompts), 1) if prompts else 0,
            },
            "top_projects_by_events": {
                clean_project(k): v for k, v in acc.project_events.most_common(15)
            },
            "monthly_tokens": {m: dict(c) for m, c in sorted(acc.month_tok.items())},
            "busiest_days_active_hours": {
                day: round(sec / 3600, 2) for day, sec in busiest
            },
        },
        "history": read_history(home),
        "stats_cache": read_stats_cache(home),
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze Claude Code usage.")
    parser.add_argument(
        "--home",
        default=os.path.expanduser("~/.claude"),
        help="Path to the Claude Code state dir (default: ~/.claude).",
    )
    parser.add_argument(
        "--idle-cap",
        type=int,
        default=300,
        help="Gaps longer than this (seconds) count as away time and are "
        "excluded from active time (default: 300).",
    )
    parser.add_argument(
        "--billing",
        choices=["auto", BILLING_INCLUDED, BILLING_METERED],
        default="auto",
        help="Billing regime. 'included' = subscription / enterprise seat "
        "with included usage (list-price cost is notional; 1h cache TTL is "
        "free upside). 'metered' = API key / usage credits / usage-based "
        "contract (cache-write TTL affects the real bill). 'auto' (default) "
        "infers it from the observed 1h-vs-5m cache-write split.",
    )
    args = parser.parse_args()
    projects_root = os.path.join(args.home, "projects")
    acc = Accumulator(args.idle_cap)
    scan_transcripts(projects_root, acc)
    compute_time(acc)
    report = build_report(acc, args.home, args.billing)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

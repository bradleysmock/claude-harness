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
import re
import os
import statistics

# Notional list prices, USD per 1M tokens: (input, output, cache_read,
# cache_write_1h). Used only for a comparative cost estimate; a Max/Pro
# subscriber is not billed this.
PRICES = {
    "claude-opus-4-8": (5.0, 25.0, 0.5, 10.0),
    "claude-opus-4-7": (5.0, 25.0, 0.5, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3, 6.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.1, 2.0),
}
DEFAULT_PRICE = (5.0, 25.0, 0.5, 10.0)


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
        self.claude_time = 0.0
        self.human_time = 0.0
        self.active_time = 0.0
        self.idle_excluded = 0.0
        self.sessions = collections.defaultdict(list)

    def record_usage(self, model, usage, epoch):
        fields = (
            ("input", usage.get("input_tokens", 0)),
            ("output", usage.get("output_tokens", 0)),
            ("cache_creation", usage.get("cache_creation_input_tokens", 0)),
            ("cache_read", usage.get("cache_read_input_tokens", 0)),
        )
        for key, value in fields:
            self.tok[model][key] += value
        self.model_turns[model] += 1
        if epoch is None:
            return
        bucket = month_of(epoch)
        for key, value in fields:
            self.month_tok[bucket][key] += value


def scan_assistant(record, acc):
    msg = record.get("message", {})
    model = msg.get("model", "unknown")
    request_id = record.get("requestId")
    usage = msg.get("usage", {})
    epoch = parse_ts(record.get("timestamp"))
    sid = record.get("sessionId")
    side = bool(record.get("isSidechain"))
    if request_id and request_id not in acc.seen_requests and usage:
        acc.seen_requests.add(request_id)
        acc.record_usage(model, usage, epoch)
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
                    scan_assistant(record, acc)
                elif kind == "user":
                    scan_user(record, acc)
                elif kind == "system" and sid:
                    epoch = parse_ts(record.get("timestamp"))
                    if epoch:
                        acc.sessions[sid].append((epoch, "system"))


def compute_time(acc):
    for events in acc.sessions.values():
        events.sort(key=lambda item: item[0])
        for index in range(1, len(events)):
            gap = events[index][0] - events[index - 1][0]
            if gap <= 0:
                continue
            if gap > acc.idle_cap:
                acc.idle_excluded += gap
                continue
            acc.active_time += gap
            acc.day_active[day_of(events[index][0])] += gap
            if events[index][1] == "human":
                acc.human_time += gap
            else:
                acc.claude_time += gap


def estimate_cost(tok):
    total = 0.0
    by_model = {}
    for model, counts in tok.items():
        p_in, p_out, p_read, p_write = PRICES.get(model, DEFAULT_PRICE)
        cost = (
            counts.get("input", 0) * p_in
            + counts.get("output", 0) * p_out
            + counts.get("cache_read", 0) * p_read
            + counts.get("cache_creation", 0) * p_write
        ) / 1_000_000
        if cost:
            by_model[model] = round(cost, 2)
        total += cost
    return round(total, 2), by_model


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


def build_report(acc, home):
    def hours(seconds):
        return round(seconds / 3600, 1)

    totals = collections.Counter()
    for counts in acc.tok.values():
        for key, value in counts.items():
            totals[key] += value
    input_side = totals["input"] + totals["cache_creation"] + totals["cache_read"]
    cache_pct = round(100 * totals["cache_read"] / input_side, 1) if input_side else 0
    cost_total, cost_by_model = estimate_cost(acc.tok)
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
            "model_turns": dict(acc.model_turns.most_common()),
            "tokens_total": dict(totals),
            "tokens_by_model": {m: dict(c) for m, c in acc.tok.items()},
            "cache_read_pct_of_input": cache_pct,
            "notional_cost_usd": cost_total,
            "notional_cost_by_model": cost_by_model,
            "top_tools_main": dict(acc.tools_main.most_common(20)),
            "top_skills": dict(acc.skills.most_common(15)),
            "top_plugins": dict(acc.plugins.most_common(10)),
            "tool_results": acc.tool_results,
            "tool_errors": acc.tool_errors,
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
    args = parser.parse_args()
    projects_root = os.path.join(args.home, "projects")
    acc = Accumulator(args.idle_cap)
    scan_transcripts(projects_root, acc)
    compute_time(acc)
    report = build_report(acc, args.home)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

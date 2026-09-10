# Solution

**Ticket**: 0082
**Title**: Notify the lead when autopilot-watch dispatches need attention

## Approach

After `run_tick`'s dispatch call returns (or raises `OSError`), re-read the
target ticket's `status.md` and classify the outcome purely from that
field — `done` is success, anything else is needs-attention with a
one-line reason. A needs-attention outcome appends to a durable log and
fires a best-effort desktop notification (macOS `osascript`, Linux
`notify-send`, silently skipped if neither exists). `cli_status` surfaces
a summary of that log. Separately, document a zero-code "watch via
Claude" pattern using the existing `/loop` skill.

## Components

| Component | Responsibility |
|---|---|
| `autopilot_watch.py`: `_classify_outcome` | Pure function: (pre-dispatch status known to be `solution`, post-dispatch `status.md` read) → `(needs_attention, reason)` |
| `autopilot_watch.py`: `_append_needs_attention` | Append one JSON line (ticket, reason, status, timestamp) to `needs-attention.jsonl` |
| `autopilot_watch.py`: `_notify_desktop` | Best-effort `osascript`/`notify-send` shell-out; catches every failure, never raises |
| `autopilot_watch.py`: `run_tick` | Wire classification + logging + notification in after the existing dispatch call |
| `autopilot_watch.py`: `cli_status` | Read `needs-attention.jsonl`; add count + latest entry to the status text |
| `commands/autopilot-watch.md` | New section documenting the `/loop`-based conversational-notification pattern |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Classify from `status.md` only, never log/stdout text | Matches this repo's own structural-signal convention (e.g. the critic's finding-header format) — free-text parsing is fragile and was explicitly ruled out in requirements |
| OS-native notification tools, no new dependency | `osascript`/`notify-send` ship with the OS; adding a Python notification library would be new supply-chain surface for a best-effort nicety |
| `/loop`-based Claude-side watching, not new code | The harness already ships this skill; documenting its use against `bin/autopilot-watch status` is a zero-risk, zero-new-code channel for the "through Claude" half of the ask |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1        | Unit      | each post-dispatch status (`done`, `changes-requested`, unchanged `solution`, `implementing`, `review-ready`, unrecognized) classifies correctly |
| FR-2        | Unit      | an `OSError` dispatch failure classifies needs-attention with the error text |
| FR-3        | Unit      | `run_tick`'s return dict carries `needs_attention`/`reason` alongside existing fields |
| FR-4        | Unit      | a needs-attention outcome appends exactly one durable line; a success outcome appends none |
| FR-5        | Unit      | notification helper invoked only on needs-attention; an injected failing subprocess call never propagates |
| FR-6        | Unit      | `cli_status` reports count + latest entry when the log is non-empty, and zero/none cleanly when absent/empty |
| FR-7        | Doc-wiring| `autopilot-watch.md` documents the `/loop` pattern |

## Tradeoffs

- **Chose OS-native best-effort notification over a guaranteed channel
  because**: there is no reliable, dependency-free way to guarantee
  delivery from a plain Python script to an arbitrary lead's attention —
  best-effort plus a durable log (which never silently loses information)
  is the honest tradeoff.
- **Accepting risk of**: a lead who never runs `/loop` or checks `status`
  still has to notice the desktop notification or find the log — this
  ticket removes the *need* to poll blindly, it doesn't guarantee the
  lead sees it instantly.

## Risks

- Desktop notifications are OS-specific and untested on Linux in this
  session — mitigated by the try-then-skip ordering and full exception
  containment; absence of either tool degrades to log-only, not a crash.

## Implementation Order

1. Unit tests for `_classify_outcome`, `_append_needs_attention`,
   `_notify_desktop`, updated `run_tick`, and updated `cli_status` — red
   first.
2. Implement the three new functions and wire them into `run_tick`.
3. Update `cli_status` to surface the needs-attention summary.
4. Update `commands/autopilot-watch.md` with the `/loop` pattern.
5. Confirm tests green; confirm no behavior change to a successful
   dispatch beyond the new no-op classification check.

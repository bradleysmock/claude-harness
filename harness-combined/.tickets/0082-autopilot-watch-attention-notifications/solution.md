# Solution

**Ticket**: 0082
**Title**: Notify the lead when autopilot-watch dispatches need attention

## Approach

After `run_tick`'s dispatch call returns (or raises `OSError`), re-read the
target ticket's `status.md` inside a guard that itself never raises — an
empty or unrecognized status string (including one from a `status.md`
with no `status:` field) takes the ordinary per-status reason path;
`done` is success; a raised exception (missing worktree/file, other
`OSError`) takes a separate "ticket state unreadable" reason. Either
needs-attention path appends to a durable, plain-append log and fires a
best-effort desktop notification: `osascript` on macOS, `notify-send` on
Linux, silently skipped if neither exists. The notification body reaches
the AppleScript exclusively through an environment variable, read via
`system attribute "<name>"` — never a CLI argument, never embedded in the
`-e` script string — closing both the AppleScript-source-injection path
and the flag-shaped-argv-misparsing path a CLI-argument-based design would
leave open. `cli_status` surfaces a summary of the log, tolerating a
malformed trailing line exactly like the existing dispatch-log reader
does. Separately, document a zero-code "watch via Claude" pattern using
the existing `/loop` skill.

## Components

| Component | Responsibility |
|---|---|
| `autopilot_watch.py`: `ClassifyResult` | Frozen dataclass (`needs_attention: bool`, `reason: str \| None`) — structured, not a bare tuple, matching `TicketInfo`'s existing precedent |
| `autopilot_watch.py`: `_classify_outcome` | Pure function: re-reads `status.md` inside its own try/except, returns a `ClassifyResult`; never raises |
| `autopilot_watch.py`: `_append_needs_attention` | Plain `open(path, "a")` append of one JSON line (ticket, reason, status, timestamp) |
| `autopilot_watch.py`: `_load_needs_attention` | Reader with the same skip-malformed-line tolerance as `load_dispatch_log` |
| `autopilot_watch.py`: `_notify_desktop` | Best-effort `osascript` (body via an env var, read with `system attribute`) / `notify-send` shell-out; catches every failure, never raises |
| `autopilot_watch.py`: `run_tick` | Wire classification + logging + notification in after the existing dispatch call |
| `autopilot_watch.py`: `cli_status` | Use `_load_needs_attention` to add count + latest entry to the status text |
| `tests/test_0078_autopilot_watch_core.py` | Update the two existing exact dict-equality assertions to the widened return shape |
| `commands/autopilot-watch.md` | New section documenting the `/loop`-based conversational-notification pattern |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Classify from `status.md` only, wrapped so re-read failure can't escape | Matches this repo's structural-signal convention, and closes the round-1 critic BLOCKER-adjacent gap where the ticket's own state vanishing mid-build would otherwise produce silence, not an alert |
| Plain append, not read/tmp-write/replace | This log is pure-append (no membership check needed before writing, unlike `dispatch-log.jsonl`); a single small `open("a")` write is POSIX-atomic — matches `_log_rejection`'s existing, already-accepted pattern |
| Reader tolerates a malformed trailing line | Mirrors `load_dispatch_log`'s existing handling of a line caught mid-write by a concurrent writer — the same hazard applies here since `cli_tick` can append while `cli_status` reads |
| `osascript` body via an environment variable, never a CLI argument or `-e`-string-interpolated | An argv-based fix (`on run argv`) only relocates the risk: `osascript`'s own option parser could still misread a flag-shaped reason as another option, with no documented `--`-end-of-options guarantee. An env var is never parsed as a CLI flag and never enters AppleScript source text — one mechanism closes both paths |
| `/loop`-based Claude-side watching, not new code | Zero-risk, zero-new-code channel for the "through Claude" half of the ask, using a skill the harness already ships |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|--------------|
| FR-1        | Unit      | each post-dispatch status classifies correctly; a `status.md` with no `status:` field classifies via the empty-string "unrecognized" reason (not the exception reason); a raised re-read failure classifies via the "ticket state unreadable" reason instead of propagating |
| FR-2        | Unit      | an `OSError` dispatch-launch failure classifies needs-attention with the error text |
| FR-3        | Unit      | `run_tick`'s return dict carries `needs_attention`/`reason`; the two pre-existing 0078 tests are updated to the widened shape |
| FR-4        | Unit      | a needs-attention outcome appends exactly one durable line; success appends none; the reader skips a malformed trailing line |
| FR-5        | Unit      | the notification helper passes the reason via `env`, never present in the constructed argument list at all (including a reason starting with `-`); invoked only on needs-attention; an injected failing subprocess call never propagates |
| FR-6        | Unit      | `cli_status` reports count + latest entry when the log is non-empty, tolerates a malformed line, and reports zero/none cleanly when absent/empty |
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
- A reason string passed via an environment variable still crosses into a
  notification UI surface — kept to a short, factual one-liner
  (status/error text only, never raw ticket-authored prose) to avoid any
  UX confusion, not a security concern.

## Implementation Order

1. Unit tests for `ClassifyResult`/`_classify_outcome` (including the
   no-`status:`-field and re-read-failure sub-cases), `_append_needs_attention`,
   `_load_needs_attention`, `_notify_desktop` (including the env-var-not-argv
   assertion), updated `run_tick`, and updated `cli_status` — red first.
2. Update the two pre-existing `test_0078_autopilot_watch_core.py`
   exact-equality assertions to the widened `run_tick` return shape.
3. Implement the new functions and wire them into `run_tick`.
4. Update `cli_status` to surface the needs-attention summary.
5. Update `commands/autopilot-watch.md` with the `/loop` pattern.
6. Confirm tests green; confirm a successful dispatch's on-disk/log
   behavior is otherwise unchanged.

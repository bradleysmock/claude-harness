# Requirements

**Ticket**: 0082
**Title**: Notify the lead when autopilot-watch dispatches need attention

## Functional Requirements

1. After a dispatch call returns without raising, `run_tick` must re-read
   the target ticket's `status.md` and classify the outcome: `done` is
   success; `changes-requested`, an unchanged `solution`, `implementing`,
   `review-ready`, or any unrecognized status is needs-attention, each
   with a stated one-line reason. If the re-read itself fails (missing
   worktree/file, missing `status` field, or any `OSError` — e.g. a
   concurrent `/cancel`/`/abandon`/`/deliver` on the same ticket while the
   dispatch was in flight) that must also classify as needs-attention,
   reason "ticket state unreadable after dispatch: <detail>" — it must
   never propagate as an uncaught exception out of `run_tick`.
2. A caught `OSError` from the dispatch call itself (the launch failure,
   distinct from FR-1's post-dispatch re-read failure) must also classify
   as needs-attention, with the error message as the reason.
3. `run_tick`'s return dict must add `needs_attention: bool` and `reason:
   str | None`, alongside the existing `dispatched`/`error`/`exit_code`
   fields. The pre-existing ticket-0078 test module
   (`tests/test_0078_autopilot_watch_core.py`) has two exact dict-equality
   assertions against `run_tick`'s return value
   (`test_run_tick_no_candidates_returns_none`,
   `test_run_tick_surfaces_dispatch_exit_code`) that this widened shape
   will fail; updating both to include the new fields is an explicit,
   required part of this ticket's implementation, not an incidental
   side effect.
4. A needs-attention outcome must append one line to
   `.harness/autopilot-watch/needs-attention.jsonl`, using a plain
   `open(path, "a")` append (matching `_log_rejection`'s existing pattern
   — POSIX guarantees a single small write is atomic, and this log is
   pure append, never read-then-rewritten) — durable, never overwritten,
   never silently dropped. Any reader of this file must skip a line that
   fails to parse as JSON rather than raise, mirroring
   `load_dispatch_log`'s existing tolerance for a line caught mid-write by
   a concurrent writer.
5. A needs-attention outcome must trigger a best-effort OS desktop
   notification: try `osascript` (macOS) then `notify-send` (Linux), in
   that order; any failure (command missing, non-zero exit, timeout) must
   be caught and ignored — it must never raise or block the tick. The
   reason/body text must never be embedded into the `osascript` AppleScript
   source string — `-e` parses its argument as AppleScript, not opaque
   data, so a reason containing a quote otherwise closes the string early
   and injects further AppleScript, including shell execution. The script
   must read the body via `on run argv` / `item 1 of argv`, passing the
   reason as a separate `subprocess` argument, never string-interpolated
   into the `-e` script text.
6. `cli_status` must report a needs-attention summary read from
   `needs-attention.jsonl` (with the same malformed-line tolerance as
   FR-4): a count of entries and the most recent one's ticket and reason;
   an absent or empty log must report cleanly as zero, never error.
7. `commands/autopilot-watch.md` must document a "watch via Claude"
   pattern: running the `/loop` skill in an interactive session on an
   interval, with a prompt to check `bin/autopilot-watch status` and
   report any needs-attention entries conversationally — no new code,
   documentation only.

## Non-Functional Requirements

1. The desktop-notification mechanism must not require any new
   third-party dependency — it must shell out to whatever OS-native tool
   is present and skip silently if none is.
2. Classification must be based solely on the ticket's on-disk
   `status.md`, never on parsing free-form log or stdout text.

## Test Strategy

| Type       | Rationale                                                               |
|------------|----------------------------------------------------------------------------|
| Unit       | `run_tick` classifies each post-dispatch status (`done`, `changes-requested`, unchanged `solution`, `implementing`, `review-ready`, unrecognized) correctly |
| Unit       | A post-dispatch `status.md` re-read failure (missing file/field, `OSError`) classifies needs-attention rather than propagating |
| Unit       | An `OSError` dispatch-launch failure is classified needs-attention with the error text as reason |
| Unit       | Updated exact-equality assertions in the pre-existing `test_0078_autopilot_watch_core.py` tests pass against the widened return shape |
| Unit       | The notification helper passes the reason as a separate argv element, never interpolated into the AppleScript source; is invoked only on needs-attention; a failing underlying OS command never propagates |
| Unit       | `cli_status` includes a needs-attention count/summary derived from the log file, tolerates a malformed trailing line, and reports cleanly when the log is absent/empty |
| Doc-wiring | `commands/autopilot-watch.md` documents the `/loop`-based conversational-notification pattern |

## Acceptance Criteria

- A dispatch resulting in `done` writes no needs-attention entry and
  triggers no notification attempt.
- A dispatch resulting in `changes-requested`, a stuck/unrecognized
  status, a post-dispatch re-read failure, or a launch error writes
  exactly one needs-attention entry with a non-empty reason and triggers
  the notification helper.
- A reason string containing a double quote or backslash cannot alter the
  executed AppleScript — verified by constructing the actual subprocess
  argument list and asserting the reason is a separate argv element, not
  embedded in the script text.
- `bin/autopilot-watch status` reports the needs-attention count and the
  latest entry's ticket and reason when the log is non-empty; reports
  zero/none cleanly otherwise, and tolerates a malformed trailing line.
- `commands/autopilot-watch.md` documents the `/loop`-based pattern for
  conversational notification via an interactive Claude Code session.

## Open Questions

None.

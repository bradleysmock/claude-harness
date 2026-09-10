# Requirements

**Ticket**: 0082
**Title**: Notify the lead when autopilot-watch dispatches need attention

## Functional Requirements

1. After a dispatch call returns without raising, `run_tick` must re-read
   the target ticket's `status.md` and classify the outcome: `done` is
   success; `changes-requested`, an unchanged `solution`, `implementing`,
   `review-ready`, or any unrecognized status is needs-attention, each
   with a stated one-line reason.
2. A caught `OSError` from the dispatch call must also classify as
   needs-attention, with the error message as the reason — folded into
   the same classification as FR-1, not a separate code path.
3. `run_tick`'s return dict must add `needs_attention: bool` and `reason:
   str | None`, alongside the existing `dispatched`/`error`/`exit_code`
   fields.
4. A needs-attention outcome must append one line to
   `.harness/autopilot-watch/needs-attention.jsonl` (ticket, reason,
   status, timestamp) — durable, never overwritten, never silently
   dropped.
5. A needs-attention outcome must trigger a best-effort OS desktop
   notification: try `osascript` (macOS) then `notify-send` (Linux), in
   that order; any failure (command missing, non-zero exit, timeout) must
   be caught and ignored — it must never raise or block the tick.
6. `cli_status` must report a needs-attention summary read from
   `needs-attention.jsonl`: a count of entries and the most recent one's
   ticket and reason; an absent or empty log must report cleanly as zero,
   never error.
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
| Unit       | An `OSError` dispatch failure is classified needs-attention with the error text as reason |
| Unit       | The notification helper is invoked only on needs-attention, never on success; a failing underlying OS command never propagates |
| Unit       | `cli_status` includes a needs-attention count/summary derived from the log file, and reports cleanly when the log is absent/empty |
| Doc-wiring | `commands/autopilot-watch.md` documents the `/loop`-based conversational-notification pattern |

## Acceptance Criteria

- A dispatch resulting in `done` writes no needs-attention entry and
  triggers no notification attempt.
- A dispatch resulting in `changes-requested`, a stuck/unrecognized
  status, or a launch error writes exactly one needs-attention entry with
  a non-empty reason and triggers the notification helper.
- `bin/autopilot-watch status` reports the needs-attention count and the
  latest entry's ticket and reason when the log is non-empty; reports
  zero/none cleanly otherwise.
- `commands/autopilot-watch.md` documents the `/loop`-based pattern for
  conversational notification via an interactive Claude Code session.

## Open Questions

None.

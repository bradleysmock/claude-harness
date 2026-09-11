# Spec Coverage Map

**Ticket**: 0082-autopilot-watch-attention-notifications
**Threshold**: 0.5 (Jaccard token overlap)

| Requirement ID | Kind | Requirement Text | Covering Spec(s) |
|---|---|---|---|
| FR-1 | FR | After a dispatch call returns without raising, `run_tick` must re-read | — |
| FR-2 | FR | A caught `OSError` from the dispatch call itself (the launch failure, | — |
| FR-3 | FR | `run_tick`'s return dict must add `needs_attention: bool` and `reason: | — |
| FR-4 | FR | A needs-attention outcome must append one line to | — |
| FR-5 | FR | A needs-attention outcome must trigger a best-effort OS desktop | — |
| FR-6 | FR | `cli_status` must report a needs-attention summary read from | — |
| FR-7 | FR | `commands/autopilot-watch.md` must document a "watch via Claude" | — |
| AC-1 | AC | A dispatch resulting in `done` writes no needs-attention entry and | — |
| AC-2 | AC | A dispatch resulting in `changes-requested`, a stuck/unrecognized | — |
| AC-3 | AC | A reason string containing a double quote, backslash, or a leading `-` | — |
| AC-4 | AC | `bin/autopilot-watch status` reports the needs-attention count and the | — |
| AC-5 | AC | `commands/autopilot-watch.md` documents the `/loop`-based pattern for | — |

## Uncovered

- FR-1 (FR): After a dispatch call returns without raising, `run_tick` must re-read
- FR-2 (FR): A caught `OSError` from the dispatch call itself (the launch failure,
- FR-3 (FR): `run_tick`'s return dict must add `needs_attention: bool` and `reason:
- FR-4 (FR): A needs-attention outcome must append one line to
- FR-5 (FR): A needs-attention outcome must trigger a best-effort OS desktop
- FR-6 (FR): `cli_status` must report a needs-attention summary read from
- FR-7 (FR): `commands/autopilot-watch.md` must document a "watch via Claude"
- AC-1 (AC): A dispatch resulting in `done` writes no needs-attention entry and
- AC-2 (AC): A dispatch resulting in `changes-requested`, a stuck/unrecognized
- AC-3 (AC): A reason string containing a double quote, backslash, or a leading `-`
- AC-4 (AC): `bin/autopilot-watch status` reports the needs-attention count and the
- AC-5 (AC): `commands/autopilot-watch.md` documents the `/loop`-based pattern for

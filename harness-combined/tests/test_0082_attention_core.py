"""Unit tests for autopilot_watch.py's needs-attention primitives (ticket 0082).

Three independent pieces, none of which touch `run_tick` yet:

* `_classify_outcome` — decides success vs. needs-attention from the target
  ticket's on-disk `status.md` alone, never from log or stdout text, and never
  raises. An empty or unrecognized status string is ordinary control flow; only
  a failed *read* takes the separate "unreadable" reason.
* `_append_needs_attention` / `_load_needs_attention` — a durable, greppable
  JSONL log. Pure append (never read-then-rewritten), so a plain `open(path,
  "a")` write is enough, matching `_log_rejection`; the reader skips a
  malformed line exactly as `load_dispatch_log` already does.
* `_notify_desktop` — best-effort OS notification. The reason text reaches the
  AppleScript only through an environment variable, so it is never parsed as
  AppleScript source and never parsed as a CLI option.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

import autopilot_watch as watch

#: The real notifier, captured before the root conftest's autouse fixture
#: replaces the module attribute with a no-op. The notify tests below are the
#: ones that must exercise the genuine shell-out path (with `subprocess.run`
#: itself stubbed), so they call through this reference rather than the
#: patched attribute.
notify_desktop = watch._notify_desktop

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_ticket_info(tmp_path: Path, status_text: str | None) -> watch.TicketInfo:
    """A `TicketInfo` whose `ticket_dir` holds the given `status.md` body.

    `status_text=None` writes no `status.md` at all, which is what a ticket
    removed mid-build by a concurrent `/cancel`, `/abandon`, or `/deliver`
    looks like to a post-dispatch re-read. The pre-dispatch `status` field is
    deliberately seeded as `solution` — the stale snapshot `run_tick` already
    holds — so a test that passes by reading that field instead of re-reading
    the file would be visibly wrong.
    """
    worktree_dir = tmp_path / ".worktrees" / "0001-foo"
    ticket_dir = worktree_dir / ".tickets" / "0001-foo"
    ticket_dir.mkdir(parents=True)
    if status_text is not None:
        (ticket_dir / "status.md").write_text(status_text, encoding="utf-8")
    return watch.TicketInfo(
        number="0001",
        slug="foo",
        full_slug="0001-foo",
        worktree_dir=worktree_dir,
        ticket_dir=ticket_dir,
        status="solution",
        approved_at="2026-09-11",
        approved_commit="abcdef1",
    )


# ---------------------------------------------------------------------------
# _classify_outcome
# ---------------------------------------------------------------------------


def test_classify_done_is_success(tmp_path: Path) -> None:
    ticket_info = make_ticket_info(tmp_path, "status: done\nticket: 0001\n")
    assert watch._classify_outcome(ticket_info) == watch.ClassifyResult(
        needs_attention=False, reason=None
    )


@pytest.mark.parametrize(
    "status", ["changes-requested", "solution", "implementing", "review-ready", "banana"]
)
def test_classify_non_done_status_needs_attention(tmp_path: Path, status: str) -> None:
    """Every status other than `done` is needs-attention, and the reason quotes
    the status actually observed so the log says *which* state it stalled in."""
    ticket_info = make_ticket_info(tmp_path, f"status: {status}\nticket: 0001\n")
    result = watch._classify_outcome(ticket_info)
    assert result.needs_attention is True
    assert result.reason == f"unrecognized post-dispatch status: '{status}'"


def test_classify_status_md_without_status_field_uses_empty_status_reason(tmp_path: Path) -> None:
    """A `status.md` that exists but carries no `status:` field parses to the
    empty string (`ticket.parse_status`'s `fields.get("status", "")`). That is
    not an exception, so it must take the ordinary unrecognized-status reason,
    never the "unreadable" one."""
    ticket_info = make_ticket_info(tmp_path, "ticket: 0001\ntitle: no status field here\n")
    result = watch._classify_outcome(ticket_info)
    assert result.needs_attention is True
    assert result.reason == "unrecognized post-dispatch status: ''"


def test_classify_missing_status_md_is_unreadable_reason(tmp_path: Path) -> None:
    ticket_info = make_ticket_info(tmp_path, None)
    result = watch._classify_outcome(ticket_info)
    assert result.needs_attention is True
    assert result.reason is not None
    assert result.reason.startswith("ticket state unreadable after dispatch:")


def test_classify_unreadable_status_md_does_not_raise(tmp_path: Path) -> None:
    """A directory where `status.md` should be makes `read_text` raise
    `IsADirectoryError` — an `OSError` that is not `FileNotFoundError`, so this
    exercises the guard's breadth rather than just the missing-file case."""
    ticket_info = make_ticket_info(tmp_path, None)
    (ticket_info.ticket_dir / "status.md").mkdir()
    result = watch._classify_outcome(ticket_info)
    assert result.needs_attention is True
    assert result.reason is not None
    assert result.reason.startswith("ticket state unreadable after dispatch:")


def test_classify_result_is_frozen() -> None:
    result = watch.ClassifyResult(needs_attention=True, reason="stalled")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.needs_attention = False  # type: ignore[misc]  # asserting immutability


# ---------------------------------------------------------------------------
# _append_needs_attention / _load_needs_attention
# ---------------------------------------------------------------------------


def test_append_needs_attention_writes_one_record(tmp_path: Path) -> None:
    watch._append_needs_attention(tmp_path, "0001", "stalled at implementing", "implementing")
    log_path = tmp_path / ".harness" / "autopilot-watch" / "needs-attention.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["ticket"] == "0001"
    assert record["reason"] == "stalled at implementing"
    assert record["status"] == "implementing"
    assert "ts" in record


def test_append_needs_attention_appends_without_overwriting(tmp_path: Path) -> None:
    watch._append_needs_attention(tmp_path, "0001", "first reason", "changes-requested")
    watch._append_needs_attention(tmp_path, "0002", "second reason", "implementing")
    entries = watch._load_needs_attention(
        tmp_path / ".harness" / "autopilot-watch" / "needs-attention.jsonl"
    )
    assert [entry["ticket"] for entry in entries] == ["0001", "0002"]
    assert [entry["reason"] for entry in entries] == ["first reason", "second reason"]


def test_load_needs_attention_absent_file_is_empty(tmp_path: Path) -> None:
    assert watch._load_needs_attention(tmp_path / "nope.jsonl") == []


def test_load_needs_attention_empty_file_is_empty(tmp_path: Path) -> None:
    log_path = tmp_path / "needs-attention.jsonl"
    log_path.write_text("", encoding="utf-8")
    assert watch._load_needs_attention(log_path) == []


def test_load_needs_attention_skips_malformed_trailing_line(tmp_path: Path) -> None:
    """A concurrent `cli_tick` append can be caught mid-write by a `cli_status`
    read — the same hazard `load_dispatch_log` already tolerates."""
    log_path = tmp_path / "needs-attention.jsonl"
    log_path.write_text(
        json.dumps({"ticket": "0001", "reason": "one", "status": "done", "ts": 1.0})
        + "\n"
        + '{"ticket": "0002", "reason": "half-writ',
        encoding="utf-8",
    )
    entries = watch._load_needs_attention(log_path)
    assert [entry["ticket"] for entry in entries] == ["0001"]


# ---------------------------------------------------------------------------
# _notify_desktop
# ---------------------------------------------------------------------------


class _RecordedRun:
    """Captures every `subprocess.run` call `_notify_desktop` makes."""

    def __init__(self, raise_for: tuple[str, ...] = (), returncode: int = 0) -> None:
        self.calls: list[dict[str, object]] = []
        self._raise_for = raise_for
        self._returncode = returncode

    def __call__(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        self.calls.append({"args": args, "kwargs": kwargs})
        if args[0] in self._raise_for:
            raise FileNotFoundError(f"{args[0]}: command not found")
        return subprocess.CompletedProcess(args, self._returncode)

    @property
    def commands(self) -> list[str]:
        return [str(call["args"][0]) for call in self.calls]  # type: ignore[index]  # args is a list

    def args_of(self, command: str) -> list[str]:
        for call in self.calls:
            args = call["args"]
            assert isinstance(args, list)
            if args[0] == command:
                return [str(item) for item in args]
        raise AssertionError(f"{command} was never invoked; saw {self.commands}")

    def flat_args(self) -> list[str]:
        flattened: list[str] = []
        for call in self.calls:
            args = call["args"]
            assert isinstance(args, list)
            flattened.extend(str(item) for item in args)
        return flattened

    def env_of(self, index: int = 0) -> dict[str, str]:
        kwargs = self.calls[index]["kwargs"]
        assert isinstance(kwargs, dict)
        env = kwargs.get("env")
        assert isinstance(env, dict)
        return env


def test_notify_passes_reason_via_env_not_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _RecordedRun()
    monkeypatch.setattr(watch.subprocess, "run", recorded)
    reason = "unrecognized post-dispatch status: 'changes-requested'"

    notify_desktop("0001", reason)

    assert recorded.commands[0] == "osascript"
    assert reason in recorded.env_of().values()
    assert reason not in recorded.flat_args()


@pytest.mark.parametrize(
    "reason",
    [
        '-e do shell script "touch /tmp/pwned"',
        '" & (do shell script "id") & "',
        "back\\slash and \"quote\" together",
        "--title=spoofed",
    ],
)
def test_notify_hostile_reason_never_reaches_osascript_argv_or_script_source(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """The reason must be data, never syntax and never an option.

    `-e` parses its argument as AppleScript *source*, so an embedded quote
    could close the string early and append further AppleScript (including
    `do shell script`). Passing the reason as a plain positional argument only
    relocates the hazard: `osascript`'s own option parser offers no documented
    `--` end-of-options guarantee, so a flag-shaped reason risks being read as
    another option. An environment variable is neither AppleScript source nor a
    CLI token, which is why the assertion here is the strong one — the reason
    appears in `env` and *nowhere* in the `osascript` argument list, not even
    as a substring of one argument.
    """
    recorded = _RecordedRun()
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", reason)

    assert reason in recorded.env_of().values()
    for argument in recorded.args_of("osascript"):
        assert reason not in argument


@pytest.mark.parametrize("reason", ["--title=spoofed", "-e do shell script \"id\""])
def test_notify_send_separates_options_from_a_flag_shaped_reason(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """`notify-send` reads its body positionally and has no env-var equivalent,
    so the reason necessarily appears in its argv. Unlike `osascript`, it parses
    options with GLib's `GOptionContext`, whose documented behaviour is that a
    bare `--` ends option parsing — so the flag-shaped case is closed by putting
    `--` ahead of the positionals rather than by an environment variable. The
    reason still travels in `env` as well, so both notifiers see it.
    """
    recorded = _RecordedRun(raise_for=("osascript",))
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", reason)

    args = recorded.args_of("notify-send")
    assert "--" in args
    assert args.index("--") < args.index(reason)


def test_notify_applescript_reads_body_with_system_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _RecordedRun()
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", "stalled at implementing")

    script = recorded.calls[0]["args"][-1]  # type: ignore[index]  # args is a list
    assert isinstance(script, str)
    assert "system attribute" in script
    assert "display notification" in script
    assert "stalled at implementing" not in script


def test_notify_uses_argument_list_and_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung notifier must not be able to block the tick, and no call may be
    assembled as a shell string."""
    recorded = _RecordedRun()
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", "stalled")

    for call in recorded.calls:
        assert isinstance(call["args"], list)
        kwargs = call["kwargs"]
        assert isinstance(kwargs, dict)
        assert kwargs.get("shell") is not True
        assert kwargs.get("timeout") is not None


def test_notify_falls_through_to_notify_send_when_osascript_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _RecordedRun(raise_for=("osascript",))
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", "stalled")

    assert recorded.commands == ["osascript", "notify-send"]


def test_notify_gives_up_quietly_when_no_notifier_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither tool installed must degrade to log-only, not to a raised tick."""
    recorded = _RecordedRun(raise_for=("osascript", "notify-send"))
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", "stalled")  # must not raise

    assert recorded.commands == ["osascript", "notify-send"]


def test_notify_contains_a_timeout_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung notifier surfaces as `TimeoutExpired`, which is a
    `SubprocessError` rather than an `OSError` — the guard must cover both, or a
    wedged `osascript` would take the whole tick down with it."""
    attempted: list[str] = []

    def timing_out_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        attempted.append(args[0])
        raise subprocess.TimeoutExpired(args, 5)

    monkeypatch.setattr(watch.subprocess, "run", timing_out_run)

    notify_desktop("0001", "stalled")  # must not raise

    assert attempted == ["osascript", "notify-send"]


def test_notify_stops_after_first_notifier_that_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """`osascript` present means macOS: a non-zero exit there is a failed
    best-effort attempt, not a reason to also try the Linux notifier."""
    recorded = _RecordedRun(returncode=1)
    monkeypatch.setattr(watch.subprocess, "run", recorded)

    notify_desktop("0001", "stalled")

    assert recorded.commands == ["osascript"]

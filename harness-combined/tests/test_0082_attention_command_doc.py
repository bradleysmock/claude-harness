"""Doc-wiring tests for the needs-attention half of commands/autopilot-watch.md
(ticket 0082).

The "watch via Claude" pattern is documentation-only by design: it composes the
`/loop` skill the harness already ships rather than adding a second notification
channel in code. These tests hold the doc to naming the pieces a lead actually
needs — the skill, an interval, the command the loop runs, and the durable log
that survives a missed desktop notification.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).parent.parent / "commands" / "autopilot-watch.md"

#: `/loop 20m …` — the skill name followed by a real duration. Anchored to the
#: invocation's shape rather than scanning for a loose substring, so prose that
#: merely happens to contain "min" cannot satisfy it.
_LOOP_INVOCATION_RE = re.compile(r"/loop\s+\d+\s*(?:s|m|min|h)\b")


def _content() -> str:
    return DOC.read_text(encoding="utf-8")


def test_documents_the_loop_skill_with_an_interval() -> None:
    content = _content()
    assert "/loop" in content
    assert _LOOP_INVOCATION_RE.search(content), (
        "the doc must show a concrete /loop invocation carrying an interval, "
        f"matching {_LOOP_INVOCATION_RE.pattern}"
    )


def test_identifies_where_the_loop_skill_comes_from() -> None:
    """`/loop` is a Claude Code built-in, not a harness command — a lead who
    greps `commands/` for it finds nothing, so the doc has to say so."""
    content = _content()
    assert "built-in" in content.lower()


def test_documented_loop_prompt_checks_the_status_subcommand() -> None:
    """The loop has to be told what to look at, and `status` is the one place
    that now aggregates needs-attention entries."""
    content = _content()
    assert "bin/autopilot-watch status" in content


def test_names_the_durable_needs_attention_log() -> None:
    content = _content()
    assert ".harness/autopilot-watch/needs-attention.jsonl" in content


def test_states_the_notification_is_best_effort() -> None:
    content = _content()
    assert "best-effort" in content.lower()


def test_documents_what_counts_as_needing_attention() -> None:
    content = _content()
    assert "changes-requested" in content


def test_preexisting_sections_are_intact() -> None:
    """This ticket adds a section; it must not displace the 0078 content."""
    content = _content()
    for heading in ("## Steps", "## Subcommands", "## What it dispatches", "## Scope"):
        assert heading in content

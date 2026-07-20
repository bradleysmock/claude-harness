"""Reconcile critic findings across repair-loop rounds by stable identity (ticket 0062).

The repair loop (``build-ticket.md`` Step 7 / 7a) re-spawns the critic fresh each round with
no memory of prior findings. :func:`reconcile` gives it per-finding identity — classifying
the current round's findings against the prior round's by :func:`gates.finding.finding_key`
(``file:line:severity:code``) — so the loop can report *which* findings were fixed, persisted,
or newly introduced, not just an aggregate count.

:func:`marker_for_key` / :func:`harvest_keys` mirror
:mod:`gates.comment_deduplicator`'s hidden-marker round-trip (there: a sha256 hash embedded in
a PR comment body; here: the plain key tuple embedded in ``critic-findings.md``), so each round
is stateless — the prior round's keys are harvested back out of the persisted file rather than
carried in memory across sessions.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from gates.finding import Finding, finding_key

#: Severities reconcile() classifies; MINOR/OBS are dropped (FR-6).
_MUST_FIX = frozenset({"BLOCKER", "MAJOR"})

#: Hidden marker carrying a finding's stable key, embedded in critic-findings.md.
_MARKER_RE = re.compile(r"<!-- harness-finding-key (?P<key>[^\n]+?) -->")

#: A top-level round/escalation section heading in critic-findings.md.
_SECTION_RE = re.compile(r"^## ", re.MULTILINE)

FindingKey = tuple[str, int | None, str, str]


@dataclass(frozen=True)
class ReconciliationResult:
    """The outcome of reconciling one round's findings against the prior round's."""

    fixed: list[FindingKey]
    persisted: list[Finding]
    new: list[Finding]


def reconcile(prev: list[Finding], curr: list[Finding]) -> ReconciliationResult:
    """Classify ``curr`` against ``prev`` by :func:`finding_key`, multiset semantics (FR-7).

    Both lists are filtered to BLOCKER/MAJOR before classifying (FR-6) — MINOR/OBS entries
    never appear in the result. Takes only pre-built ``Finding`` lists; no parsing or file I/O
    (FR-3) — callers harvest ``prev`` via :func:`harvest_keys` beforehand.
    """
    prev_fixable = [f for f in prev if f.severity in _MUST_FIX]
    curr_fixable = [f for f in curr if f.severity in _MUST_FIX]

    prev_counts = Counter(finding_key(f) for f in prev_fixable)
    curr_counts = Counter(finding_key(f) for f in curr_fixable)

    persisted: list[Finding] = []
    new: list[Finding] = []
    remaining_persisted = dict(prev_counts)
    for f in curr_fixable:
        key = finding_key(f)
        if remaining_persisted.get(key, 0) > 0:
            persisted.append(f)
            remaining_persisted[key] -= 1
        else:
            new.append(f)

    fixed: list[FindingKey] = []
    remaining_curr = dict(curr_counts)
    for f in prev_fixable:
        key = finding_key(f)
        if remaining_curr.get(key, 0) > 0:
            remaining_curr[key] -= 1
        else:
            fixed.append(key)

    return ReconciliationResult(fixed=fixed, persisted=persisted, new=new)


def marker_for_key(key: FindingKey) -> str:
    """The hidden marker a ``critic-findings.md`` entry carries so a later round can harvest it."""
    file_, line_, severity_, code_ = key
    return f"<!-- harness-finding-key {file_}:{line_}:{severity_}:{code_} -->"


def latest_section(text: str) -> str:
    """Return the text of the last top-level (``## ``) section in ``text``.

    ``critic-findings.md`` is append-only, so its last ``## Round`` section is always
    the most recently persisted round (an ``### Escalation diagnosis`` sub-section, if
    present, nests under its round and is not itself a ``## `` boundary). Scoping to
    just that section
    before calling :func:`harvest_keys` is what makes ``prev`` mean "the immediately
    preceding round" rather than every round ever appended (FR-3) — a full-file harvest
    would double-count a key that persisted across two or more prior rounds, since each
    round re-embeds a fresh marker for every finding it still reports. Returns ``text``
    unchanged when it has no ``## `` heading.
    """
    starts = [m.start() for m in _SECTION_RE.finditer(text)]
    if not starts:
        return text
    return text[starts[-1] :]


def harvest_keys(text: str) -> list[FindingKey]:
    """Recover every :func:`marker_for_key` marker in ``text``, in document order.

    Never raises on a malformed marker body — a match that doesn't split into exactly 4
    ``:``-delimited fields, or whose line field is neither ``'None'`` nor an integer, is
    skipped rather than raising.
    """
    keys: list[FindingKey] = []
    for m in _MARKER_RE.finditer(text):
        parts = m.group("key").split(":", 3)
        if len(parts) != 4:
            continue
        file_, line_str, severity_, code_ = parts
        if line_str == "None":
            line_: int | None = None
        else:
            try:
                line_ = int(line_str)
            except ValueError:
                continue
        keys.append((file_, line_, severity_, code_))
    return keys

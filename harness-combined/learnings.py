# harness-combined/learnings.py
"""Candidate-learnings mechanics: parse gate/critic findings into normalized
records, sanitize attacker-influenceable text, dedupe against `_learnings.md`,
and append accepted entries.

Centralizes the sanitize/dedupe/append logic `/deliver` and `/harvest-learnings`
both need, so the injection-relevant trust boundary lives in one tested place
instead of two prose copies. The write path only ever assembles a line from the
validated template fields (`date`, `gate`, `ticket`, `pattern`) — raw findings
text is never held next to a write.

Stdlib only. subprocess is never used here.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STUB_HEADER = """# Learnings

Must-fix patterns surfaced through gate failures and post-build reviews. The harness loads this file as context at the start of every `/problem` and `/build` so the model avoids repeating the same mistakes. **Lead-curated** — `/deliver` and `/harvest-learnings` append to it, but only after the lead accepts each candidate, and only via a template-field-only write path (they never overwrite existing entries or write raw extracted text). The machine's raw failure trail lives in `.harness/memory.db` (read by `memory(action="retrieve", ...)` before each repair attempt) and is intentionally separate from this file.

Format: one entry per pattern, dated, terse. The `ticket` field is the originating ticket number, or `multi` for a recurring cross-ticket pattern from `/harvest-learnings`.

```
<date> | <gate> | <ticket> | <pattern>
```

Examples (delete these once real entries accumulate):

```
2026-04-12 | type_check | 0031  | Public APIs annotate Optional[X], not X or None — older mypy in CI rejects PEP 604.
2026-04-18 | security   | 0042  | subprocess.run with any user-derived value: argv list + shell=False, no exceptions.
2026-05-02 | test       | multi | Async tests need asyncio_mode = auto in pyproject; without it they silently pass.
```

Add a new line when you encounter a repeated mistake or a pattern worth enforcing. Keep entries terse — the model uses them as guardrails, not documentation. Prune freely; older entries that no longer apply should be removed by hand.
"""

# Fixed, token-scoped directive set (FR-6) — deterministic, not a "when in doubt"
# judgment call. Matched against each sentence's depunctuated, lowercased words,
# anywhere in the sentence (no positional blind spot).
_DIRECTIVE_TOKENS = {"claude", "assistant", "ignore", "disregard", "system", "now"}
_DIRECTIVE_PHRASE = "you must"

_HEADING_LINE_RE = re.compile(r"(?m)^##.*$")
_TAG_RE = re.compile(r"<[^<>]*>")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_NON_PRINTABLE_RE = re.compile(r"[^\x20-\x7E]")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")

_PATTERN_LENGTH_CAP = 120


def _sentence_has_directive(sentence: str) -> bool:
    lowered = sentence.lower()
    if _DIRECTIVE_PHRASE in lowered:
        return True
    tokens = {w.lower() for w in _WORD_RE.findall(sentence)}
    return bool(tokens & _DIRECTIVE_TOKENS)


def sanitize_pattern(message: str) -> str | None:
    """Neutralize attacker-influenceable text before it is ever displayed or
    written. Applied in this exact order:

    1. strip heading lines, 2. strip XML-like tags, 3. strip any sentence
    containing a directive token/phrase, 4. collapse newlines, 5. restrict to
    printable characters, 6. remove the `|` field delimiter, 7. length-cap at
    120 chars. Returns None when nothing survives sanitization (reject the
    candidate entirely)."""
    text = message or ""
    text = _HEADING_LINE_RE.sub("", text)
    text = _TAG_RE.sub("", text)

    sentences = _SENTENCE_SPLIT_RE.split(text)
    sentences = [s for s in sentences if not _sentence_has_directive(s)]
    text = " ".join(sentences)

    text = text.replace("\n", " ")
    text = _NON_PRINTABLE_RE.sub("", text)
    text = text.replace("|", "/")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = text[:_PATTERN_LENGTH_CAP]

    return text or None


_SECTION_RE = re.compile(r"(?m)^## (.+)$")


def _sections(text: str) -> list[tuple[str, str]]:
    matches = list(_SECTION_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1).strip(), text[start:end]))
    return out


_STATUS_RE = re.compile(r"\*\*Status\*\*:\s*(PASS|FAIL)")
_BULLET_RE = re.compile(r"(?m)^-\s+(.*)$")
_CODE_BULLET_RE = re.compile(r"^`[^`]*`\s*(?:\[`[^`]*`\])?:\s*(.*)$")
_SEVERITY_TOKENS = ("BLOCKER", "MAJOR", "MINOR", "OBS")


def _gate_bullet_message(bullet: str) -> str:
    m = _CODE_BULLET_RE.match(bullet)
    return m.group(1).strip() if m else bullet


def _gate_severity(bullet: str) -> str:
    upper = bullet.upper()
    for tok in _SEVERITY_TOKENS:
        if tok in upper:
            return tok
    if "ERROR" in upper:
        return "BLOCKER"
    if "WARNING" in upper:
        return "MINOR"
    return "BLOCKER"


def _parse_gate_findings(text: str) -> list[tuple[str, str, str, int]]:
    """Return (gate, message, severity, order) tuples for every failing bullet
    in a `FAIL`-status `## <gate-name>` section."""
    out: list[tuple[str, str, str, int]] = []
    order = 0
    for heading, body in _sections(text):
        status = _STATUS_RE.search(body)
        if not status or status.group(1) != "FAIL":
            continue
        for bullet_match in _BULLET_RE.finditer(body):
            bullet = bullet_match.group(1).strip()
            if not bullet or bullet.lower() == "clean":
                continue
            message = _gate_bullet_message(bullet)
            if not message:
                continue
            out.append((heading, message, _gate_severity(bullet), order))
            order += 1
    return out


# Tolerates the documented `**BLOCKER-1 — summary.**` template (parse-gate-findings.md
# Step 2c) plus reasonable punctuation variance (a colon or hyphen instead of an em
# dash, no numeric suffix, no trailing period) — critic rounds are model-authored and
# don't always hit the template byte-for-byte.
_CRITIC_ENTRY_RE = re.compile(
    r"\*\*(BLOCKER|MAJOR)(?:-\d+)?\s*[—:-]\s*(.+?)\.?\*\*", re.DOTALL
)


def _parse_critic_findings(text: str) -> list[tuple[str, str, str, int]]:
    """Return (gate, message, severity, order) tuples for every BLOCKER/MAJOR
    finding across every `## Round`/`## Escalation` section. `gate` is always
    the literal string `critic` (never the round heading or date)."""
    out: list[tuple[str, str, str, int]] = []
    order = 0
    for _heading, body in _sections(text):
        for m in _CRITIC_ENTRY_RE.finditer(body):
            severity, summary = m.group(1), m.group(2).strip()
            summary = _WHITESPACE_RE.sub(" ", summary)
            if not summary:
                continue
            out.append(("critic", summary, severity, order))
            order += 1
    return out


def parse_findings(
    text: str, source_kind: str, ticket_number: str, today: str
) -> list[dict[str, str]]:
    """Parse `gate-findings.md` (`source_kind="gate"`) or `critic-findings.md`
    (`source_kind="critic"`) text into normalized, sanitized candidate records
    `{date, gate, ticket, pattern, severity}`, prioritized (severity first, then
    recency) and capped at 5. Absent/empty input, or input with no qualifying
    section, returns an empty list."""
    if not text or not text.strip():
        return []

    raw = _parse_critic_findings(text) if source_kind == "critic" else _parse_gate_findings(text)

    scored: list[tuple[int, int, dict[str, str]]] = []
    for gate, message, severity, order in raw:
        pattern = sanitize_pattern(message)
        if not pattern:
            continue
        record = {
            "date": today,
            "gate": gate,
            "ticket": ticket_number,
            "pattern": pattern,
            "severity": severity,
        }
        high_priority = severity in ("BLOCKER", "MAJOR")
        scored.append((0 if high_priority else 1, -order, record))

    scored.sort(key=lambda s: (s[0], s[1]))
    return [record for _, _, record in scored[:5]]


def _normalize(pattern: str) -> str:
    return _WHITESPACE_RE.sub(" ", pattern.strip().lower())


def dedupe_candidates(
    candidates: list[dict[str, str]], existing_text: str
) -> list[dict[str, str]]:
    """Drop any candidate whose pattern (normalized: lowercased, whitespace
    collapsed) already appears in `existing_text` — the text after the *last*
    `|` on each line, so both the 4-field (`date | gate | ticket | pattern`) and
    legacy 3-field (`date | gate | pattern`) formats dedupe correctly."""
    existing_patterns = set()
    for line in existing_text.splitlines():
        if "|" not in line:
            continue
        pattern = line.rsplit("|", 1)[-1]
        existing_patterns.add(_normalize(pattern))

    survivors = []
    for c in candidates:
        if _normalize(c["pattern"]) in existing_patterns:
            continue
        survivors.append(c)
    return survivors


def create_stub(learnings_path: Path) -> bool:
    """Write `STUB_HEADER` to `learnings_path` if it does not already exist.
    Returns True when the stub was written, False when the file already existed
    (skip, do not overwrite — `/init`'s existing-file contract)."""
    if learnings_path.exists():
        return False
    learnings_path.parent.mkdir(parents=True, exist_ok=True)
    learnings_path.write_text(STUB_HEADER, encoding="utf-8")
    return True


def append_learnings(
    learnings_path: Path, accepted: list[dict[str, str]]
) -> list[str]:
    """Append accepted candidates to `learnings_path`, creating it with
    `STUB_HEADER` first if absent. Existing content is byte-for-byte preserved —
    only new lines are added after it. Returns the appended lines (for the
    caller to report). No-op (returns `[]`) when `accepted` is empty."""
    if not accepted:
        return []

    create_stub(learnings_path)

    lines = [
        f"{c['date']} | {c['gate']} | {c['ticket']} | {c['pattern']}" for c in accepted
    ]
    with learnings_path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    return lines


def _main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: learnings <sanitize|candidates|dedupe|append|stub> ...",
            file=sys.stderr,
        )
        return 2
    cmd = argv[0]

    if cmd == "stub":
        if len(argv) < 2:
            print("usage: learnings stub <learnings_path>", file=sys.stderr)
            return 2
        created = create_stub(Path(argv[1]))
        print(json.dumps({"created": created}))
        return 0

    if cmd == "sanitize":
        if len(argv) < 2:
            print("usage: learnings sanitize <message>", file=sys.stderr)
            return 2
        print(json.dumps(sanitize_pattern(argv[1])))
        return 0

    if cmd == "candidates":
        positional = argv[1:]
        if len(positional) < 4:
            print(
                "usage: learnings candidates <gate|critic> <ticket> <today> "
                "<findings_path>",
                file=sys.stderr,
            )
            return 2
        source_kind, ticket_number, today, findings_path = positional[:4]
        path = Path(findings_path)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        print(json.dumps(parse_findings(text, source_kind, ticket_number, today)))
        return 0

    if cmd == "dedupe":
        positional = argv[1:]
        if len(positional) < 2:
            print(
                "usage: learnings dedupe <learnings_path> <candidates.json>",
                file=sys.stderr,
            )
            return 2
        learnings_path, candidates_path = Path(positional[0]), Path(positional[1])
        existing_text = (
            learnings_path.read_text(encoding="utf-8") if learnings_path.exists() else ""
        )
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        print(json.dumps(dedupe_candidates(candidates, existing_text)))
        return 0

    if cmd == "append":
        positional = argv[1:]
        if len(positional) < 2:
            print(
                "usage: learnings append <learnings_path> <accepted.json>",
                file=sys.stderr,
            )
            return 2
        learnings_path, accepted_path = Path(positional[0]), Path(positional[1])
        accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
        for line in append_learnings(learnings_path, accepted):
            print(line)
        return 0

    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

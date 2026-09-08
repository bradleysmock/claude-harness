"""Parse per-language gate-command overrides from ``.tickets/_standards.md``.

``_standards.md`` is **operator-trusted** — lead-authored, committed to git, and
behind repo access control. An override replaces a language's default gate command
with an explicit argv list, run without a shell, so shell metacharacters in the
*argument* positions are inert by construction. The ``arg[0]`` hardening here is
defense-in-depth against an accidental shell regression downstream, not the primary
control.

The overrides live in a fenced ``[gates]`` block. Either fence form is accepted::

    ```gates
    python.lint = "ruff check . --select E,F"
    typescript.test = "npm test"
    ```

or a plain fence whose first line is the ``[gates]`` marker::

    ```
    [gates]
    python.lint = "ruff check . --select E,F"
    ```

Each value is a quoted string; its inner text is split into an argv list with
``shlex.split`` so quoted arguments survive (``--config 'a b.toml'`` stays one arg).

Parsing is **fail-closed**: any malformed line, unknown language, unmatched quote,
empty command, oversize argv, or forbidden ``arg[0]`` raises :class:`ConfigError`.
The caller must surface that as a ``CONFIG_ERROR`` gate finding rather than silently
falling back to the default commands — a misconfigured override must be visible.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from gates._scope import _compile_pattern
from gates.external import ExternalGateSpec
from models import StackName

#: Upper bound on argv length for a single override (defense-in-depth).
_MAX_ARGS = 32

#: Characters that must never appear in ``arg[0]`` (the executable/name). ``/`` is
#: included to forbid absolute/relative paths; ``..`` is checked separately.
_FORBIDDEN_ARG0_CHARS = set("/|;&><$`(){}\\!")

#: Valid languages an override may target.
_VALID_LANGUAGES = {s.value for s in StackName}

#: Overridable directory-mode gate names per language. Mirrors the gate sets in
#: each ``run_*_suite_on_dir`` (kept here rather than imported to avoid a cycle,
#: since the suites import this module). An override naming a gate outside its
#: language's set fails closed — a typo like ``python.typecheck`` (the real name
#: is ``type_check``) must be rejected, not silently ignored.
_VALID_GATES: dict[str, frozenset[str]] = {
    StackName.PYTHON.value: frozenset({"lint", "type_check", "test", "security"}),
    StackName.TYPESCRIPT.value: frozenset({"type_check", "lint", "test"}),
    StackName.GO.value: frozenset({"build", "vet", "test"}),
    StackName.RUST.value: frozenset({"check", "clippy", "test"}),
}

#: A gate name is a short identifier (e.g. ``lint``, ``type_check``, ``dep-audit``).
_GATE_RE = re.compile(r"[A-Za-z0-9_-]+")

#: Block-level settings (not ``language.gate`` command overrides) permitted inside
#: the ``[gates]`` block. The override parser skips these so a block-level knob and
#: the per-gate command overrides can share one fenced block.
_BLOCK_SETTINGS = frozenset({"parallel_gate_limit"})

#: ``parallel_gate_limit = N`` — the max concurrent gates the scheduler may run
#: (ticket 0036). Lives in the ``[gates]`` block alongside command overrides.
_PARALLEL_LIMIT_RE = re.compile(r"^parallel_gate_limit\s*=\s*(.+)$")


class ConfigError(ValueError):
    """Raised when the ``[gates]`` override block is malformed or unsafe."""


def _extract_gates_block(text: str) -> list[str] | None:
    """Return the content lines of the first fenced ``[gates]`` block, or ``None``.

    A block qualifies if its fence info string is ``gates`` or its first content
    line is the ``[gates]`` marker.
    """
    in_fence = False
    is_gates_info = False
    block: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                is_gates_info = stripped[3:].strip().lower() == "gates"
                block = []
            else:
                in_fence = False
                first = block[0].strip().lower() if block else ""
                if is_gates_info or first == "[gates]":
                    return block
            continue
        if in_fence:
            block.append(line)
    return None


def _parse_argv(value: str) -> list[str]:
    """Turn a quoted command value into a validated argv list.

    ``value`` is the raw right-hand side (including its surrounding quotes). The
    outer quotes wrap the command string; the inner text is ``shlex.split``.
    """
    if len(value) < 2 or value[0] not in "\"'" or value[-1] != value[0]:
        raise ConfigError(f"override value must be a quoted string, got {value!r}")
    inner = value[1:-1]
    try:
        argv = shlex.split(inner)
    except ValueError as exc:  # unmatched quote, etc.
        raise ConfigError(f"cannot parse override command {value!r}: {exc}") from exc
    if not argv:
        raise ConfigError(f"override command is empty: {value!r}")
    if len(argv) > _MAX_ARGS:
        raise ConfigError(
            f"override command has {len(argv)} args (max {_MAX_ARGS}): {value!r}"
        )
    arg0 = argv[0]
    if ".." in arg0 or _FORBIDDEN_ARG0_CHARS.intersection(arg0):
        raise ConfigError(
            f"override command name {arg0!r} contains a path or shell metacharacter"
        )
    return argv


def load_gate_overrides(
    standards_path: Path | str,
) -> dict[str, dict[str, list[str]]]:
    """Parse gate-command overrides from ``standards_path``.

    Returns a mapping ``language -> gate-name -> argv``. A missing file or an
    absent ``[gates]`` block yields ``{}``. Any malformed content raises
    :class:`ConfigError` (fail-closed — never silently drop an override).
    """
    path = Path(standards_path)
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc

    block = _extract_gates_block(text)
    if block is None:
        return {}

    overrides: dict[str, dict[str, list[str]]] = {}
    for raw in block:
        line = raw.strip()
        if not line or line.startswith("#") or line.lower() == "[gates]":
            continue
        if line.lower() in ("[policy]", "[external_gates]"):
            # Everything from here to the end of the fence belongs to another
            # sub-block (ticket 0074's [policy], ticket 0077's
            # [external_gates]) and is parsed elsewhere — their line shapes
            # would otherwise misparse as malformed overrides.
            break
        if "=" not in line:
            raise ConfigError(f"malformed override line (no '='): {line!r}")
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key in _BLOCK_SETTINGS:
            # Block-level setting (e.g. parallel_gate_limit), not a command
            # override — parsed separately by load_parallel_gate_limit.
            continue
        if "." not in key:
            raise ConfigError(f"override key must be '<language>.<gate>': {key!r}")
        language, _, gate = key.partition(".")
        language, gate = language.strip(), gate.strip()
        if language not in _VALID_LANGUAGES:
            raise ConfigError(f"unknown override language: {language!r}")
        if not _GATE_RE.fullmatch(gate):
            raise ConfigError(f"invalid override gate name: {gate!r}")
        valid_gates = _VALID_GATES[language]
        if gate not in valid_gates:
            raise ConfigError(
                f"unknown gate {gate!r} for {language}; "
                f"valid gates: {', '.join(sorted(valid_gates))}"
            )
        overrides.setdefault(language, {})[gate] = _parse_argv(value)
    return overrides


#: Section markers that can appear inside the `[gates]` fence, each starting
#: its own sub-block. A sub-block extractor stops at whichever of the
#: *other* markers comes next, so two sub-blocks never bleed into each other
#: regardless of which order the lead wrote them in.
_SUB_BLOCK_MARKERS = frozenset({"[policy]", "[external_gates]"})


def _extract_sub_block(block: list[str], marker: str) -> list[str] | None:
    start = None
    for index, raw in enumerate(block):
        if raw.strip().lower() == marker:
            start = index + 1
            break
    if start is None:
        return None
    end = len(block)
    for index in range(start, len(block)):
        if block[index].strip().lower() in _SUB_BLOCK_MARKERS:
            end = index
            break
    return block[start:end]


def extract_policy_block(text: str) -> list[str] | None:
    """Return the content lines of the `[policy]` sub-block, or ``None``.

    The sub-block lives inside the same fenced `[gates]` region as the command
    overrides, demarcated by a `[policy]` marker line (ticket 0074), and stops
    at a subsequent `[external_gates]` marker if present. Text extraction
    only — parsing and validation live in ``gates/policy.py``.
    """
    block = _extract_gates_block(text)
    if block is None:
        return None
    return _extract_sub_block(block, "[policy]")


def extract_external_gates_block(text: str) -> list[str] | None:
    """Return the content lines of the `[external_gates]` sub-block, or
    ``None``. Mirrors :func:`extract_policy_block` (ticket 0077) — text
    extraction only, stopping at a subsequent `[policy]` marker if present.
    """
    block = _extract_gates_block(text)
    if block is None:
        return None
    return _extract_sub_block(block, "[external_gates]")


#: Every built-in gate name across every language, plus the cross-cutting
#: gates that aren't overridable commands (so absent from `_VALID_GATES`)
#: but are still real, addressable gate names a `name` could collide with.
_BUILTIN_GATE_NAMES: frozenset[str] = frozenset(
    gate for gates_for_language in _VALID_GATES.values() for gate in gates_for_language
) | frozenset({"secrets", "coverage", "dep-audit", "sast", "commit_lint"})

_DEFAULT_EXTERNAL_TIMEOUT = 60

_EXTERNAL_GATE_LINE_RE = re.compile(r"^(?P<name>[A-Za-z0-9_-]+)\s*=\s*\{(?P<body>.*)\}\s*$")


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split ``text`` on ``sep``, ignoring any ``sep`` inside a quoted span."""
    parts: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    for char in text:
        if in_quote:
            current.append(char)
            if char == in_quote:
                in_quote = None
            continue
        if char in "\"'":
            in_quote = char
            current.append(char)
            continue
        if char == sep:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _unquote(value: str) -> str:
    if len(value) < 2 or value[0] not in "\"'" or value[-1] != value[0]:
        raise ConfigError(f"expected a quoted string, got {value!r}")
    return value[1:-1]


def _validate_bracket_expression(body: str, pattern: str) -> None:
    """Reject a reversed character range (``[z-a]``) inside one ``[...]``
    body — ``PurePosixPath.match`` accepts these silently (they just never
    match), never raising, so this is real syntax validation, not merely
    forcing the compiler's own (nonexistent, for this shape) exception."""
    index = 0
    while index < len(body):
        if index + 2 < len(body) and body[index + 1] == "-":
            start, end = body[index], body[index + 2]
            if start > end:
                raise ConfigError(
                    f"reversed character range '{start}-{end}' in scope glob {pattern!r}"
                )
            index += 3
        else:
            index += 1


def _validate_complex_glob_syntax(pattern: str) -> None:
    """Reject the malformed-bracket shapes ``PurePosixPath.match`` itself
    will not raise on: an unmatched/unclosed/out-of-order ``[``/``]``, or a
    reversed character range. ``_compile_pattern``'s fallback branch
    (``PurePosixPath.match``) never raises for any of these — it silently
    returns a predicate that just never matches anything, exactly the "gate
    silently degrades to never runs" failure this validation exists to
    prevent — so this is real syntax validation, not a compiler round-trip.
    """
    depth = 0
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "[":
            if depth > 0:
                raise ConfigError(f"nested '[' in scope glob {pattern!r}")
            depth += 1
            close = pattern.find("]", index + 1)
            if close == -1:
                raise ConfigError(f"unclosed '[' in scope glob {pattern!r}")
            _validate_bracket_expression(pattern[index + 1:close], pattern)
            depth -= 1
            index = close + 1
            continue
        if char == "]":
            raise ConfigError(f"unmatched ']' in scope glob {pattern!r}")
        index += 1


def _validate_scope(scope: str) -> None:
    """Validate every comma-separated glob, then compile each via
    ``gates/_scope.py``'s pattern compiler (kept for the empty-segment case
    it does reject, and so a future compiler change is still exercised)."""
    for segment in scope.split(","):
        segment = segment.strip()
        if not segment:
            raise ConfigError(f"empty scope glob segment in {scope!r}")
        _validate_complex_glob_syntax(segment)
        try:
            _compile_pattern(segment)
        except ValueError as exc:
            raise ConfigError(f"invalid scope glob {segment!r}: {exc}") from exc


def _parse_external_gate_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for segment in _split_top_level(body):
        segment = segment.strip()
        if not segment:
            continue
        if "=" not in segment:
            raise ConfigError(f"malformed external_gates field: {segment!r}")
        key, _, value = segment.partition("=")
        fields[key.strip()] = value.strip()
    return fields


def load_external_gates(standards_path: Path | str) -> list[ExternalGateSpec]:
    """Parse `[external_gates]` entries from `standards_path` (ticket 0077).

    Each entry: ``name = { command = "...", scope = "...", timeout = N }``.
    Fail-closed: a malformed entry, a `name` colliding with a built-in gate
    or another `[external_gates]` entry, a bad `command`/`scope`, or a
    non-positive `timeout` raises :class:`ConfigError`.
    """
    path = Path(standards_path)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc

    block = extract_external_gates_block(text)
    if block is None:
        return []

    seen_names: set[str] = set()
    specs: list[ExternalGateSpec] = []
    for raw in block:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXTERNAL_GATE_LINE_RE.match(line)
        if not match:
            raise ConfigError(f"malformed external_gates entry: {line!r}")
        name = match.group("name")
        if name in _BUILTIN_GATE_NAMES:
            raise ConfigError(
                f"external gate name {name!r} collides with a built-in gate"
            )
        if name in seen_names:
            raise ConfigError(f"duplicate external_gates entry: {name!r}")
        seen_names.add(name)

        fields = _parse_external_gate_fields(match.group("body"))
        if "command" not in fields:
            raise ConfigError(f"external_gates.{name} is missing 'command'")
        command = _parse_argv(fields["command"])

        scope: str | None = None
        if "scope" in fields:
            scope = _unquote(fields["scope"])
            _validate_scope(scope)

        timeout = _DEFAULT_EXTERNAL_TIMEOUT
        if "timeout" in fields:
            raw_timeout = fields["timeout"].strip("\"'")
            try:
                timeout = int(raw_timeout)
            except ValueError as exc:
                raise ConfigError(
                    f"external_gates.{name}.timeout must be an integer, got {raw_timeout!r}"
                ) from exc
            if timeout < 1:
                raise ConfigError(f"external_gates.{name}.timeout must be >= 1")

        specs.append(ExternalGateSpec(
            name=name, command=command, scope=scope, timeout_seconds=timeout,
        ))
    return specs


def load_parallel_gate_limit(standards_path: Path | str) -> int | None:
    """Parse ``parallel_gate_limit`` from the ``[gates]`` block of ``standards_path``.

    Returns the configured max concurrent gates (a positive int), or ``None`` when
    the file, the block, or the setting is absent — in which case the scheduler runs
    all independent gates concurrently (FR-5's "no explicit limit" default). Parsing
    is fail-closed: a non-integer or non-positive value raises :class:`ConfigError`
    so a typo is visible rather than silently ignored. The value may be bare
    (``parallel_gate_limit = 4``) or quoted (``= "4"``).
    """
    path = Path(standards_path)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc

    block = _extract_gates_block(text)
    if block is None:
        return None
    for raw in block:
        match = _PARALLEL_LIMIT_RE.match(raw.strip())
        if not match:
            continue
        value = match.group(1).strip().strip("\"'")
        try:
            limit = int(value)
        except ValueError as exc:
            raise ConfigError(
                f"parallel_gate_limit must be a positive integer, got {value!r}"
            ) from exc
        if limit < 1:
            raise ConfigError(
                f"parallel_gate_limit must be >= 1, got {limit}"
            )
        return limit
    return None

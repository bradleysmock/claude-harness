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

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from models import GateResult

#: ``skip_reason`` recorded on a GateResult produced for a scoped-out gate. Shared
#: so the exact string cannot drift between the language modules (requirements FR-4).
SKIP_REASON = "no relevant changes"

#: A bare-suffix glob such as ``*.py`` / ``*.tsx`` — ``*`` then a dotted extension
#: with no other glob metacharacter or path separator.
_SUFFIX_GLOB = re.compile(r"^\*(\.[A-Za-z0-9_.]+)$")
#: A literal filename such as ``go.mod`` / ``Cargo.toml`` — no glob metacharacter
#: and no path separator, so it matches purely on a path's last component.
_LITERAL_NAME = re.compile(r"^[^*?\[\]/]+$")


@dataclass
class GateSpec:
    """A directory-mode gate bundled with the file-scope patterns that govern it.

    ``fn`` is the gate function (``(directory, config) -> GateResult``); it is
    invoked only when :func:`has_scope_match` returns True for the current
    changed-file set. ``scope_patterns`` is a list of ``PurePosixPath.match`` globs
    (e.g. ``["*.py", "*.pyi"]``); ``None`` means "no scope declared — never skip
    this gate" (FR-6, the fail-safe default). Co-locating the scope with the
    function reference keeps the two from drifting (NFR-3).
    """

    fn: Callable[..., GateResult]
    scope_patterns: list[str] | None


def _compile_pattern(pattern: str) -> Callable[[str], bool]:
    """Compile one scope pattern into a fast per-file predicate.

    ``*.ext`` becomes a plain ``str.endswith`` and a literal filename becomes a
    basename-equality test — both O(len) string ops that avoid constructing a
    ``PurePosixPath`` per file, keeping the 10k-file worst case within NFR-1's
    10 ms budget. Any genuinely complex glob (``**``, ``?``, ``[...]`` or an
    embedded ``/``) falls back to ``PurePosixPath.match`` so semantics stay exact;
    none of the gate scopes shipped today take that path, it is forward-compat
    headroom only. Every branch matches ``PurePosixPath.match`` semantics: a bare
    suffix/name pattern matches against a path's final component regardless of
    directory depth.
    """
    suffix = _SUFFIX_GLOB.match(pattern)
    if suffix:
        ext = suffix.group(1)  # e.g. ".py"
        return lambda f: f.endswith(ext)
    if _LITERAL_NAME.match(pattern):
        anchored = "/" + pattern
        return lambda f: f == pattern or f.endswith(anchored)
    compiled = PurePosixPath  # bind locally; complex patterns keep exact semantics
    return lambda f: compiled(f).match(pattern)


def has_scope_match(
    changed_files: list[str] | None, scope_patterns: list[str] | None
) -> bool:
    """Return True when a gate with ``scope_patterns`` should run for ``changed_files``.

    Run the gate (return True) when:

    - ``changed_files`` is ``None`` — the caller computed no diff, so run everything
      (preserves pre-0030 behaviour exactly),
    - ``changed_files`` is empty — a diff was computed but is empty/unknown state,
      so run everything (FR-7 safe default),
    - ``scope_patterns`` is ``None`` — the gate declares no scope, never skip (FR-6).

    Otherwise return True iff at least one changed file matches at least one
    pattern. Patterns are compiled to fast predicates once (see
    :func:`_compile_pattern`) and ``any`` short-circuits, so a matching change is
    detected as early as possible and the no-match worst case still finishes well
    inside the 10 ms budget (NFR-1). ``"*.py"`` matches ``"src/foo.py"`` at any
    directory depth — the whole point of using path-match rather than ``fnmatch``.
    """
    if changed_files is None or not changed_files:
        return True
    if scope_patterns is None:
        return True
    predicates = [_compile_pattern(p) for p in scope_patterns]
    return any(pred(f) for f in changed_files for pred in predicates)

"""Red-gate check (ticket 0065).

Before implementation is generated for a spec, ``check_red`` runs only the
spec's newly-written test(s) — scoped to an exact node-id filter, never the
full suite — against the pre-implementation worktree and classifies the
result:

- ``RED`` — the target test(s) fail (or fail to collect because the
  not-yet-created target is missing). This is the desired TDD precondition:
  implementation may proceed.
- ``BLOCKING`` — every target test already passes. The test does not
  discriminate; it must be revised before implementation is written.
- ``TOOL_ERROR`` — the check could not run to a conclusion (runner crash,
  timeout, or the target node id never appeared in the output). Never
  conflated with ``RED``: a genuine test failure is meaningful signal, a
  broken check is not.

``next_action`` is a pure decision function, independently testable from the
classification: it turns ``(classification, attempt, max_attempts)`` into
``RETRY`` / ``ESCALATE_SKIP`` / ``PROCEED``.

Each language delegates to its module's existing directory-mode runner/parser
pair (``gates.python``, ``gates.go``, ``gates.rust``, ``gates.typescript``),
re-invoked with an exact node-id filter so the same parsing logic classifies a
single targeted run instead of the full suite.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gates import go as _go
from gates import python as _py
from gates import rust as _rust
from gates import typescript as _ts
from models import GateError

RED = "red"
BLOCKING = "blocking"
TOOL_ERROR = "tool_error"

RETRY = "retry"
ESCALATE_SKIP = "escalate_skip"
PROCEED = "proceed"

SUPPORTED_LANGUAGES = ("python", "go", "rust", "typescript")

#: Substrings (checked case-insensitively) that mark a collection/import
#: failure as attributable to the not-yet-created target — valid RED evidence
#: (FR-3) rather than a tool fault. Deliberately narrow: any other collection
#: failure (an unrelated syntax error elsewhere in the file, say) falls
#: through to TOOL_ERROR instead of a false RED.
_TARGET_MISSING_MARKERS = (
    "no module named",
    "modulenotfounderror",
    "cannot find module",
    "cannot find package",
    "undefined:",
    "unresolved import",
    "cannot find function",
    "unresolved reference",
    "error[e0432]",
    "error[e0433]",
)


class RedGateError(ValueError):
    """Caller misuse — unsupported language, empty node_ids, or a test path
    outside the worktree root. Never raised for a tool crash; that is reported
    as ``TOOL_ERROR`` instead."""


@dataclass(frozen=True)
class RedGateResult:
    classification: str  # RED | BLOCKING | TOOL_ERROR
    node_ids: tuple[str, ...]
    detail: str


def _first_line(text: str) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[0].strip() if stripped else ""


def _target_missing(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _TARGET_MISSING_MARKERS)


def _resolve_within_root(candidate: Path, root: Path) -> Path:
    """Resolve ``candidate`` and return it, or raise ``RedGateError`` if it
    escapes ``root`` — validation and normalization in one step, used both
    where the result is discarded (a pure containment check) and where the
    caller needs the resolved path back."""
    resolved = candidate.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise RedGateError(f"test path {candidate} escapes the worktree root {root}")
    return resolved


def _exact_match(wanted: str, present_id: str) -> bool:
    """Exact node-id equality — the matcher for Python and Rust, whose
    node_ids are already the runner's own fully-qualified id. Contrast with
    Go's and TypeScript's inline suffix-matchers below, which must account for
    a package/describe-path prefix the caller's bare node_id doesn't include."""
    return wanted == present_id


def _exact_alternation_pattern(node_ids: list[str]) -> str:
    """An anchored ``^(a|b|...)$`` regex matching only these exact node ids —
    shared by Go's ``-run`` and TypeScript/jest's ``-t`` filters, both of which
    take a regex rather than a literal list."""
    return "^(" + "|".join(re.escape(n) for n in node_ids) + ")$"


def _classify(
    parsed_ok: bool,
    present: set[str],
    failing: dict[str, GateError],
    node_ids: list[str],
    output: str,
    matcher: Callable[[str, str], bool],
) -> RedGateResult:
    """Classify a run against ``node_ids``.

    A collection/import error can surface two ways depending on the language
    and how badly the run broke: either nothing parses at all (``parsed_ok``
    False), or the runner emits a *file-level* id (e.g. Python's ``ERROR
    test_foo.py - ModuleNotFoundError: ...``, with no ``::test_name`` suffix)
    that never matches the exact node id(s) requested. Both cases are "we could
    not attribute a pass/fail to our target" and are handled identically: check
    the output for the not-yet-created-target marker before falling back to
    ``TOOL_ERROR``, so a genuine missing-target collection error classifies as
    ``RED`` regardless of which shape it took.
    """
    ids = tuple(node_ids)
    matched_present = (
        {pid for pid in present if any(matcher(w, pid) for w in node_ids)} if parsed_ok else set()
    )
    if not matched_present:
        if _target_missing(output):
            return RedGateResult(
                RED, ids, "collection/import error names the not-yet-created target",
            )
        detail = _first_line(output) or "runner produced no parseable output"
        return RedGateResult(
            TOOL_ERROR,
            ids,
            detail if not parsed_ok else "target node id(s) did not appear in the run output",
        )
    matched_failing = {pid: err for pid, err in failing.items() if pid in matched_present}
    if matched_failing:
        return RedGateResult(RED, ids, "target test(s) failed as expected pre-implementation")
    return RedGateResult(BLOCKING, ids, "target test(s) passed without implementation")


def _check_python(root: Path, node_ids: list[str], timeout: int) -> RedGateResult:
    # A pytest node id embeds its own path segment (`path::test`), passed
    # straight into pytest's argv — a second, independent path input beyond
    # test_file that check_red's own containment check never covers. Validate
    # it here so a node id cannot make pytest collect/execute a file outside
    # the worktree root.
    for node_id in node_ids:
        candidate = Path(node_id.split("::", 1)[0])
        _resolve_within_root(candidate if candidate.is_absolute() else root / candidate, root)
    result = _py._exec_dir(
        [
            sys.executable, "-m", "pytest", "-rA", "-q", "--tb=short",
            "-p", "no:cacheprovider", *node_ids,
        ],
        str(root), timeout=timeout,
    )
    parsed_ok, present, failing = _py._parse_pytest_report(result.output, result.returncode)
    return _classify(parsed_ok, present, failing, node_ids, result.output, matcher=_exact_match)


def _check_go(root: Path, test_file: str, node_ids: list[str], timeout: int) -> RedGateResult:
    # Scope to the package containing test_file — never the whole module
    # (`./...`). Go test names collide across packages routinely (TestCreate,
    # TestParse, ...); running the whole module and matching on bare function
    # name would let a same-named, already-passing test in an unrelated
    # package misattribute a `blocking` target as `red`. Package directory
    # scoping plus a package-qualified matcher closes both ends of that gap.
    pkg_dir = Path(test_file).parent
    target = "." if str(pkg_dir) in (".", "") else f"./{pkg_dir}"
    pattern = _exact_alternation_pattern(node_ids)
    result = _go._exec(["go", "test", "-run", pattern, "-json", target], root, timeout=timeout)
    parsed_ok, present, failing = _go._parse_go_test_json(result.output, result.returncode)
    return _classify(
        parsed_ok, present, failing, node_ids, result.output,
        matcher=lambda w, p: p.endswith("." + w),
    )


def _check_rust(root: Path, node_ids: list[str], timeout: int) -> RedGateResult:
    present: set[str] = set()
    failing: dict[str, GateError] = {}
    combined_output: list[str] = []
    for node_id in node_ids:
        result = _rust._exec(
            ["cargo", "test", "--no-fail-fast", node_id, "--", "--exact"], root, timeout=timeout,
        )
        combined_output.append(result.output)
        ok, file_present, file_failing = _rust._parse_cargo_test_output(result.output, result.returncode)
        if not ok:
            return _classify(False, set(), {}, [node_id], result.output, matcher=_exact_match)
        present |= file_present
        failing.update(file_failing)
    return _classify(
        True, present, failing, node_ids, "\n".join(combined_output), matcher=_exact_match,
    )


def _check_typescript(root: Path, test_file: str, node_ids: list[str], timeout: int) -> RedGateResult:
    rel_test_file = test_file
    pattern = _exact_alternation_pattern(node_ids)
    # jest's positional argument is matched as a regex against test file paths,
    # not a literal path — escape it so a "." or other regex metacharacter in
    # the file name (e.g. "thing.test.js") can't silently widen or break the
    # match.
    result = _ts._exec(
        ["npx", "--yes", "jest", "--no-coverage", "--json", "-t", pattern, re.escape(rel_test_file)],
        root, timeout=timeout,
    )
    parsed_ok, present, failing = _ts._parse_jest_json_present(result.stdout, root)
    return _classify(
        parsed_ok, present, failing, node_ids, result.output,
        matcher=lambda w, p: p.endswith("::" + w),
    )


def check_red(
    directory: str,
    language: str,
    test_file: str,
    node_ids: list[str],
    timeout: int = 60,
) -> RedGateResult:
    """Run only ``node_ids`` (scoped to ``test_file``) and classify the result.

    ``directory`` is the worktree root; ``test_file`` (relative to ``directory``,
    or absolute) must resolve inside it. ``node_ids`` is per-language:
    Python — full pytest node id(s) (``path::test``); Go — bare test function
    name(s); Rust — fully-qualified test name(s) (``mod::test``); TypeScript —
    the full jest ``fullName`` (describe-path-qualified, e.g. ``"my describe
    target test"`` — space-joined ancestor titles + the test's own title, as
    jest itself reports it; a bare title only equals the fullName when the test
    has no enclosing ``describe()`` block).

    Never raises for a tool crash or timeout — those are reported as
    ``TOOL_ERROR``. Raises ``RedGateError`` only for caller misuse (unsupported
    language, empty ``node_ids``, or a ``test_file`` outside ``directory``).
    """
    if language not in SUPPORTED_LANGUAGES:
        raise RedGateError(f"unsupported language: {language}")
    if not node_ids:
        raise RedGateError("node_ids must be non-empty")

    root = Path(directory)
    candidate = Path(test_file)
    resolved = _resolve_within_root(candidate if candidate.is_absolute() else root / candidate, root)
    # Every downstream _check_* helper works off this root-relative form, not
    # the raw (possibly absolute) test_file — an absolute test_file would
    # otherwise reach Go's package-directory derivation unrelativized and
    # produce a malformed `go test` target.
    rel_test_file = str(resolved.relative_to(root))

    try:
        if language == "python":
            return _check_python(root, node_ids, timeout)
        if language == "go":
            return _check_go(root, rel_test_file, node_ids, timeout)
        if language == "rust":
            return _check_rust(root, node_ids, timeout)
        return _check_typescript(root, rel_test_file, node_ids, timeout)
    except subprocess.TimeoutExpired:
        return RedGateResult(TOOL_ERROR, tuple(node_ids), f"runner timed out after {timeout}s")
    except OSError as exc:
        return RedGateResult(TOOL_ERROR, tuple(node_ids), f"runner failed to start: {exc}")


def next_action(classification: str, attempt: int, max_attempts: int) -> str:
    """Pure decision: ``(classification, attempt, max_attempts) -> action``.

    ``RED`` always proceeds. ``TOOL_ERROR`` always escalates immediately — it
    never consumes a retry, since a broken check will not self-correct via test
    revision (FR-5). ``BLOCKING`` retries while ``attempt < max_attempts``
    (``attempt`` is the attempt number that just completed), then escalates on
    budget exhaustion (FR-4/FR-6).
    """
    if classification == RED:
        return PROCEED
    if classification == TOOL_ERROR:
        return ESCALATE_SKIP
    if classification == BLOCKING:
        return RETRY if attempt < max_attempts else ESCALATE_SKIP
    raise RedGateError(f"unknown classification: {classification}")

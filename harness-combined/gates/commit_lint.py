"""Conventional-commit lint gate.

Validates that every commit on a delivery branch (those not reachable from the
base branch) conforms to the conventional-commit subject format
``type(scope): subject``. Pure Python — no external commitlint dependency.

Security posture (see solution.md Tech Choices):
- Branch and resolved base names are validated against ``_REF_RE`` before they
  reach ``git``, and every range/ref is passed after a ``--`` separator, so a
  crafted branch name cannot smuggle a ``git`` option (D-04 adv, D2-01).
- Subjects are truncated to ``_MAX_SUBJECT`` and the type token is constrained to
  the allowed set, so the ``.+`` tail cannot drive catastrophic backtracking.
- Base-branch resolution fails **closed**: an unknown base yields
  ``BASE_BRANCH_UNKNOWN`` rather than a false pass.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass

from models import GateError, GateResult

# The standard conventional-commit type set (FR-6).
DEFAULT_ALLOWED_TYPES: tuple[str, ...] = (
    "feat", "fix", "docs", "style", "refactor",
    "perf", "test", "chore", "build", "ci", "revert",
)

# Allow-list for any git ref/branch name we pass on the command line. The leading
# ``(?!-)`` anchor rejects any name beginning with ``-`` (e.g. ``--format=...``,
# ``-n``) so a ref can never be read as a git option; the char class then permits
# only the characters a real git ref needs. No shell metacharacter can pass.
_REF_RE = re.compile(r"^(?!-)[A-Za-z0-9_./-]+$")

# Merge commits are excluded from validation (solution.md: "Merge commits excluded").
_MERGE_RE = re.compile(r"^Merge ")

# Bound the backtracking surface of the trailing ``.+`` on adversarial subjects.
_MAX_SUBJECT = 200

_GIT_TIMEOUT = 5  # NFR-1: complete well under 5s for <=200 commits.


@dataclass
class CommitLintConfig:
    """Configuration for a commit-lint run.

    A dataclass (not a bag of positional args) so overrides from ``_standards.md``
    compose cleanly without a Data Clump at each call site.
    """

    allowed_types: tuple[str, ...] = DEFAULT_ALLOWED_TYPES
    require_scope: bool = False
    base_branch: str = "main"


def _compile_subject_pattern(config: CommitLintConfig) -> re.Pattern[str]:
    """Build the conventional-commit matcher for this config.

    ``type`` is an alternation over the (escaped) allowed set; ``scope`` is a
    single ``(...)`` group with no nested parens or newlines. Neither sub-pattern
    can backtrack super-linearly, so the compiled regex is ReDoS-safe.
    """
    types = "|".join(re.escape(t) for t in config.allowed_types)
    scope = r"\([^()\n]+\)"
    if config.require_scope:
        body = rf"(?:{types}){scope}: .+"
    else:
        body = rf"(?:{types})(?:{scope})?: .+"
    return re.compile(rf"^{body}$", re.DOTALL)


def _run_git(args: list[str], project_root: str) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <project_root> <args...>`` with an argument list (no shell)."""
    return subprocess.run(
        ["git", "-C", project_root, *args],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
    )


def _ref_exists(ref: str, project_root: str) -> bool:
    if not _REF_RE.match(ref):
        return False
    # ref is already validated against _REF_RE (no leading dash), so no option
    # injection is possible here; rev-parse needs no `--` separator.
    proc = _run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], project_root)
    return proc.returncode == 0


def _resolve_base_branch(config: CommitLintConfig, project_root: str) -> tuple[str | None, GateError | None]:
    """Resolve the base branch to diff against, failing closed.

    Prefers the configured base (default ``main``). If that ref does not exist,
    falls back to the remote default via ``symbolic-ref refs/remotes/origin/HEAD``,
    sanitising the extracted name against ``_REF_RE`` before trusting it. Returns
    ``(name, None)`` on success or ``(None, GateError)`` with ``BASE_BRANCH_UNKNOWN``.
    """
    if _ref_exists(config.base_branch, project_root):
        return config.base_branch, None

    sym = _run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], project_root)
    if sym.returncode == 0:
        name = sym.stdout.strip().rsplit("/", 1)[-1]
        # D2-01: the extracted name is untrusted — sanitise before use.
        if _REF_RE.match(name) and _ref_exists(name, project_root):
            return name, None

    return None, GateError(
        message=(
            f"Cannot resolve base branch '{config.base_branch}' (and no valid "
            "origin/HEAD fallback); refusing to lint against an unknown base."
        ),
        file=None,
        line=None,
        column=None,
        code="BASE_BRANCH_UNKNOWN",
        severity="error",
    )


def _parse_standards_config(text: str) -> tuple[dict[str, object], list[str]]:
    """Parse a ``## Commit Lint`` block from ``_standards.md`` text.

    Recognises ``allowed_types: [a, b, c]`` and ``require_scope: true|false``.
    Returns ``(overrides, warnings)``; a malformed value is dropped with a warning
    string rather than raising, so a bad standards file degrades to defaults.
    """
    overrides: dict[str, object] = {}
    warnings: list[str] = []

    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Commit Lint\s*$", line):
            start = i + 1
            break
    if start is None:
        return overrides, warnings

    for line in lines[start:]:
        if line.startswith("## "):  # next section — stop
            break
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("allowed_types:"):
            raw = stripped[len("allowed_types:"):].strip()
            match = re.match(r"^\[(.*)\]$", raw)
            if not match:
                warnings.append("_standards.md: 'allowed_types' must be a [comma, separated] list; using defaults.")
                continue
            items = [t.strip() for t in match.group(1).split(",") if t.strip()]
            # D2-04: an empty override list is not a valid override — fall back.
            if not items:
                warnings.append("_standards.md: 'allowed_types' is empty; using defaults.")
                continue
            invalid = [t for t in items if not re.match(r"^[a-z]+$", t)]
            if invalid:
                warnings.append(f"_standards.md: ignoring invalid type token(s) {invalid}; using defaults.")
                continue
            overrides["allowed_types"] = tuple(items)
        elif stripped.startswith("require_scope:"):
            raw = stripped[len("require_scope:"):].strip().lower()
            if raw in ("true", "false"):
                overrides["require_scope"] = raw == "true"
            else:
                warnings.append("_standards.md: 'require_scope' must be true or false; using default.")

    return overrides, warnings


def _apply_standards(config: CommitLintConfig, project_root: str) -> tuple[CommitLintConfig, list[GateError]]:
    """Overlay ``.tickets/_standards.md`` overrides onto ``config`` (FR-9)."""
    from pathlib import Path

    standards = Path(project_root) / ".tickets" / "_standards.md"
    if not standards.is_file():
        return config, []

    try:
        text = standards.read_text(encoding="utf-8")
    except OSError as exc:
        return config, [GateError(
            message=f"_standards.md: unreadable ({exc}); using defaults.",
            file=None, line=None, column=None, code="STANDARDS_PARSE", severity="warning",
        )]

    overrides, warn_strs = _parse_standards_config(text)
    warnings = [GateError(
        message=w, file=None, line=None, column=None, code="STANDARDS_PARSE", severity="warning",
    ) for w in warn_strs]

    # Narrow the loosely-typed override values explicitly (no blanket ignore).
    raw_types = overrides.get("allowed_types")
    allowed_types = raw_types if isinstance(raw_types, tuple) else config.allowed_types
    raw_scope = overrides.get("require_scope")
    require_scope = raw_scope if isinstance(raw_scope, bool) else config.require_scope

    merged = CommitLintConfig(
        allowed_types=allowed_types,
        require_scope=require_scope,
        base_branch=config.base_branch,
    )
    return merged, warnings


def run(
    branch: str,
    project_root: str,
    config: CommitLintConfig | None = None,
) -> GateResult:
    """Lint every commit on ``branch`` not reachable from the base branch.

    Returns a ``GateResult`` whose ``passed`` reflects error-severity findings only
    (parse warnings never block). Fails closed on an invalid branch name, an
    unresolved base branch, or a failed ``git`` invocation.
    """
    start = time.monotonic()
    config = config or CommitLintConfig()

    def result(passed: bool, errors: list[GateError]) -> GateResult:
        return GateResult(
            gate="commit_lint",
            passed=passed,
            errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # D-04 adv: reject a branch name that could be read as a git option / injection.
    if not _REF_RE.match(branch):
        return result(False, [GateError(
            message=f"Invalid branch name: {branch!r}",
            file=None, line=None, column=None, code="INVALID_BRANCH", severity="error",
        )])

    config, warnings = _apply_standards(config, project_root)

    # Every git touch — base resolution *and* the log — must fail closed. A hung
    # `git` (TimeoutExpired), a crashed subprocess, or an unspawnable binary
    # (OSError: missing / not executable / EACCES) can never be read as "no
    # offending commits". OSError covers FileNotFoundError and PermissionError.
    try:
        base, base_error = _resolve_base_branch(config, project_root)
        if base_error is not None:
            return result(False, [*warnings, base_error])
        assert base is not None  # narrowed by base_error is None

        proc = _run_git(
            ["log", f"{base}..{branch}", "--no-merges", "--format=%H %s", "--"],
            project_root,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        # No path or command echoed — just the failure class (fail closed).
        return result(False, [*warnings, GateError(
            message=f"git invocation failed ({type(exc).__name__}); failing closed.",
            file=None, line=None, column=None, code="GIT_ERROR", severity="error",
        )])

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        first = detail[0] if detail else f"git log exited {proc.returncode}"
        return result(False, [*warnings, GateError(
            message=f"git log failed for '{base}..{branch}': {first}",
            file=None, line=None, column=None, code="GIT_ERROR", severity="error",
        )])

    pattern = _compile_subject_pattern(config)
    errors: list[GateError] = list(warnings)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, subject = line.partition(" ")
        short = sha[:7]  # FR-4: file field is exactly sha[:7]
        # --no-merges already drops merge commits; guard belt-and-suspenders.
        if _MERGE_RE.match(subject):
            continue
        if not pattern.match(subject[:_MAX_SUBJECT]):
            errors.append(GateError(
                # file field repurposed as commit SHA reference; subject bounded
                # to the same window we match, so an adversarial subject can't
                # bloat the output.
                message=f"{short}: {subject[:_MAX_SUBJECT]}",
                file=short,
                line=None,
                column=None,
                code="COMMIT_LINT",
                severity="error",
            ))

    passed = not any(e.severity == "error" for e in errors)
    return result(passed, errors)

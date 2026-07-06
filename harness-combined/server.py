"""
harness-combined MCP server.
Provides mechanical tools — gates (text + directory mode), files, memory, DAG — for Claude.
No API key required. Claude Code is the orchestrator.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure this directory is on the path so local modules resolve.
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

from dag import DAGResolver
from gates import GateTimeoutConfig, run_suite_for, run_suite_on_dir
from gates.commit_lint import CommitLintConfig
from gates.commit_lint import run as run_commit_lint
from gates.config import ConfigError, load_gate_overrides
from gates.doctor import DoctorError, format_report, run_doctor
from memory import SQLiteFailureMemory
from models import (
    GateError,
    GateResult,
    LanguageResult,
    Spec,
    StackName,
    Task,
    TaskSpec,
)

mcp = FastMCP("harness")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _harness_dir(project_root: str) -> Path:
    return Path(project_root) / ".harness"


def _db_path(project_root: str) -> str:
    return str(_harness_dir(project_root) / "memory.db")


def _memory(project_root: str) -> SQLiteFailureMemory:
    db = _db_path(project_root)
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    return SQLiteFailureMemory(db)


def _find_artifact(run_id: str, project_root: str) -> Path | None:
    results_dir = _harness_dir(project_root) / "results"
    exact = results_dir / f"{run_id}.json"
    if exact.exists():
        return exact
    matches = sorted(results_dir.glob(f"*{run_id}*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _apply_patch(implementation: str, diff: str) -> tuple[str, str | None]:
    """Apply a unified diff via `patch`. Returns (patched_text, error_or_None)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_patch_"))
    try:
        target = tmpdir / "implementation"
        target.write_text(implementation, encoding="utf-8")
        result = subprocess.run(
            ["patch", "--no-backup-if-mismatch", str(target)],
            input=diff, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return implementation, result.stderr.strip() or result.stdout.strip()
        return target.read_text(encoding="utf-8"), None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _load_spec_module(path: Path) -> dict[str, Any]:
    """Exec a spec file with a fake harness module injected."""
    harness_mod = types.ModuleType("harness")
    harness_mod.Spec = Spec  # type: ignore[attr-defined]
    sys.modules["harness"] = harness_mod
    try:
        namespace: dict[str, Any] = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        spec = namespace.get("spec")
        if not isinstance(spec, Spec):
            raise ValueError("Spec file did not define a 'spec' variable of type Spec")
        return spec.to_dict()
    finally:
        sys.modules.pop("harness", None)


def _load_task_module(path: Path) -> Task:
    """Exec a task file with fake harness module injected."""
    harness_mod = types.ModuleType("harness")
    harness_mod.Task = Task  # type: ignore[attr-defined]
    harness_mod.TaskSpec = TaskSpec  # type: ignore[attr-defined]
    sys.modules["harness"] = harness_mod
    try:
        namespace: dict[str, Any] = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        task = namespace.get("task")
        if not isinstance(task, Task):
            raise ValueError("Task file did not define a 'task' variable of type Task")
        return task
    finally:
        sys.modules.pop("harness", None)


def _detect_language(directory: str) -> str:
    """Detect project language from marker files."""
    d = Path(directory)
    if (d / "go.mod").exists():
        return "go"
    if (d / "Cargo.toml").exists():
        return "rust"
    if (d / "tsconfig.json").exists() or (d / "package.json").exists():
        return "typescript"
    # Python: require a project descriptor, not just *.py files
    if (d / "pyproject.toml").exists() or (d / "setup.py").exists() or (d / "setup.cfg").exists():
        return "python"
    # Fallback: scan for *.py files only if no other marker found
    if any(d.rglob("*.py")):
        return "python"
    return "python"  # default


# Manifest files that mark each stack. Detection is manifest-only (FR-1): loose
# source files (e.g. bare *.py) no longer trigger a stack — operators declare a
# project descriptor. Order mirrors StackName's canonical ordering.
_STACK_MANIFESTS: dict[StackName, tuple[str, ...]] = {
    StackName.PYTHON: ("pyproject.toml", "setup.py", "setup.cfg"),
    StackName.TYPESCRIPT: ("package.json", "tsconfig.json"),
    StackName.GO: ("go.mod",),
    StackName.RUST: ("Cargo.toml",),
}

# Vendored / cache directories are never scanned for manifests — both for speed
# (NFR-2: node_modules alone holds thousands of package.json files) and to avoid
# false positives from a dependency's own manifests.
_SCAN_SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "target", "__pycache__"}


def _scan_roots(directory: str) -> list[Path]:
    """The resolved root plus each immediate, contained, non-vendored subdirectory.

    Exactly one level deep is scanned (FR-1). A subdirectory is included only if it
    resolves to a path still under the resolved root — a symlink escaping the root
    is skipped (path-containment guard) so a link out of the worktree can't drag an
    unrelated project's manifests into detection.
    """
    root = Path(directory).resolve()
    roots = [root]
    try:
        children = sorted(root.iterdir())
    except OSError:
        return roots
    for child in children:
        if child.name in _SCAN_SKIP:
            continue
        try:
            if not child.is_dir():
                continue
            resolved = child.resolve()
            resolved.relative_to(root)  # containment: raises ValueError if it escapes
        except (OSError, ValueError):
            continue
        roots.append(resolved)
    return roots


def _detect_stacks(directory: str) -> list[StackName]:
    """Detect every language stack present via a uniform root + one-level manifest
    scan, so a polyglot worktree is never silently gated as a single language.

    Manifest-only (FR-1): a stack is present iff one of its manifest files sits in
    the root or an immediate (contained, non-vendored) subdirectory. Returns
    StackName members in canonical order, each at most once. Deeper trees, raw
    source files, and symlinked-out subdirectories are ignored.
    """
    roots = _scan_roots(directory)
    detected: list[StackName] = []
    for stack in StackName:  # canonical order
        manifests = _STACK_MANIFESTS[stack]
        if any((r / m).exists() for r in roots for m in manifests):
            detected.append(stack)
    return detected


def _format_polyglot_findings(results: list[LanguageResult], directory: str) -> str:
    """Render aggregated gate results as the ``gate-findings.md`` body.

    Pure and independently unit-testable — the pinned reference for the heading
    format the critic reads. With more than one language it prefixes a
    ``**Languages detected**`` header and labels each section
    ``## {language} / {gate}``; with a single language it emits neither the plural
    header nor the language prefix (``## {gate}``), preserving the pre-polyglot
    single-language report shape (FR-8). ``directory`` is accepted for interface
    stability with callers that annotate the report with the gated path.
    """
    multi = len(results) > 1
    lines: list[str] = []
    if multi:
        langs = ", ".join(str(lr.language) for lr in results)
        lines += [f"**Languages detected**: {langs}", ""]
    for lr in results:
        for gr in lr.results:
            lines.append(f"## {lr.language} / {gr.gate}" if multi else f"## {gr.gate}")
            lines += ["", f"**Status**: {'PASS' if gr.passed else 'FAIL'}",
                      f"**Duration**: {gr.duration_ms}ms", ""]
            if gr.errors:
                for e in gr.errors:
                    where = e.file or "?"
                    loc = f"{where}:{e.line}" if e.line is not None else where
                    lines.append(f"- `{loc}` [`{e.code}`]: {e.message}")
            else:
                lines.append("clean")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _config_error_payload(exc: ConfigError, standards_path: str) -> str:
    """Fail-closed response for a malformed ``[gates]`` override block.

    Returns ``passed: false`` with a single ``CONFIG_ERROR`` finding and does
    **not** fall back to the default gate commands — a misconfigured override must
    never silently pass as if it were absent.
    """
    finding = GateResult(
        gate="config", passed=False,
        errors=[GateError(
            message=str(exc), file=standards_path, line=None, column=None,
            code="CONFIG_ERROR", severity="error",
        )],
        duration_ms=0,
    )
    return json.dumps({"passed": False, "gates": [finding.to_dict()]}, indent=2)


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def gate_run(implementation: str, tests: str, language: str, project_root: str) -> str:
    """
    Write implementation and tests to a temp directory and run the full gate suite.
    Returns JSON. On full pass: {"passed": true, "duration_ms": N}.
    On failure: the failing gate result with structured errors.
    Stops at first failure (fail-fast).

    Each error has: message, file, line, column, code, severity.
    """
    try:
        config = GateTimeoutConfig.from_directory(Path(project_root))
        results = run_suite_for(language, implementation, tests, project_root, config=config)
        if all(r.passed for r in results):
            return json.dumps({
                "passed": True,
                "duration_ms": sum(r.duration_ms for r in results),
            })
        failed = next(r for r in results if not r.passed)
        return json.dumps(failed.to_dict(), indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Gate execution failed: {e}"})


@mcp.tool()
def gate_run_on_dir(directory: str, language: str, project_root: str, fail_fast: bool = True) -> str:
    """
    Run gates against a project directory (worktree or project root).
    language: "auto" to detect from marker files, or "python"/"typescript"/"go"/"rust".
    fail_fast=True (default): stop at first failure — use during /build repair loop.
    fail_fast=False: run all gates regardless — use for /gate to write gate-findings.md.

    Returns JSON. Pass: {"passed": true, "language": ...}.
    Fail+fast: the failing gate result. Fail+full: {"passed": false, "language": ..., "gates": [...]}.
    """
    try:
        config = GateTimeoutConfig.from_directory(Path(directory))
        # The coverage gate reads its thresholds from `.tickets/_thresholds.yaml`
        # and writes its `gate-findings.json` sidecar into `.tickets/<active-slug>/`.
        # Both must resolve against the *directory being gated* (the worktree/branch),
        # NOT `project_root` (the main repo) — otherwise the sidecar the gate writes
        # and the branch copy the `/deliver` preflight reads would never coincide.
        # The same `_standards.md` also carries the operator's [gates] command
        # overrides. A malformed override block fails closed (CONFIG_ERROR) — it
        # must never silently fall back to the default commands.
        standards_path = str(Path(directory) / ".tickets" / "_standards.md")
        try:
            overrides_map = load_gate_overrides(standards_path)
        except ConfigError as exc:
            return _config_error_payload(exc, standards_path)

        # Normalise to StackName so detected and explicit stacks share one type.
        # An unknown explicit language raises ValueError here (caught below), the
        # same fail path as an unsupported language reaching the suite dispatch.
        if language == "auto":
            stacks: list[StackName] = _detect_stacks(directory) or [
                StackName(_detect_language(directory))
            ]
        else:
            stacks = [StackName(language)]
        # Gate every detected stack; a polyglot worktree must not pass by
        # gating only one language (FR-2/FR-4). A single explicit language keeps
        # the original response shape for back-compat with /build (FR-8).
        lang_results: list[LanguageResult] = []
        for stack in stacks:
            overrides = overrides_map.get(str(stack))
            kwargs: dict[str, Any] = dict(
                fail_fast=fail_fast, standards_path=standards_path,
                base_ref="main", config=config,
            )
            # Forward overrides only when present so suites/fakes without the
            # parameter keep working.
            if overrides:
                kwargs["overrides"] = overrides
            results = run_suite_on_dir(stack, directory, **kwargs)
            lang_results.append(LanguageResult(stack, results))
            if fail_fast and not all(r.passed for r in results):
                failed = next(r for r in results if not r.passed)
                payload = failed.to_dict()
                payload["language"] = str(stack)
                return json.dumps(payload, indent=2)

        tagged = [(lr.language, r) for lr in lang_results for r in lr.results]
        single = len(stacks) == 1
        if all(r.passed for _, r in tagged):
            if single:
                return json.dumps({"passed": True, "language": str(stacks[0])})
            return json.dumps({
                "passed": True,
                "languages": [str(s) for s in stacks],
                "findings_md": _format_polyglot_findings(lang_results, directory),
            })
        if single:
            return json.dumps({
                "language": str(stacks[0]),
                "gates": [r.to_dict() for _, r in tagged],
                "passed": False,
            }, indent=2)
        return json.dumps({
            "languages": [str(s) for s in stacks],
            "gates": [{**r.to_dict(), "language": str(st)} for st, r in tagged],
            "passed": False,
            "findings_md": _format_polyglot_findings(lang_results, directory),
        }, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except (OSError, ImportError, RuntimeError) as e:
        return json.dumps({"error": f"Gate execution failed: {e}"})


@mcp.tool()
def commit_lint(branch: str, project_root: str, require_scope: bool = False) -> str:
    """
    Lint every commit on `branch` that is not reachable from the base branch
    (default `main`) against the conventional-commit format `type(scope): subject`.

    require_scope=True additionally fails commits that omit the `(scope)`.
    Allowed types and require_scope may be overridden by a `## Commit Lint` block
    in `.tickets/_standards.md`.

    Returns JSON: the GateResult — {"gate": "commit_lint", "passed": bool,
    "errors": [{message, file, line, column, code, severity}], "duration_ms": N}.
    Each failing commit is one error whose `file` is the 7-char SHA and whose
    `message` is "<short-sha>: <subject>". Fails closed (passed=false) on an
    invalid branch name, an unresolved base branch, or a git error.
    """
    try:
        result = run_commit_lint(branch, project_root, CommitLintConfig(require_scope=require_scope))
        return json.dumps(result.to_dict(), indent=2)
    except FileNotFoundError:
        return json.dumps({"error": "git executable not found on PATH"})
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        # subprocess.SubprocessError (incl. TimeoutExpired) is not an OSError —
        # catch it explicitly so a git hang can't surface as an unhandled crash.
        return json.dumps({"error": f"commit_lint failed: {type(e).__name__}"})


@mcp.tool()
def spec_load(spec_id: str, project_root: str) -> str:
    """
    Load a spec from .harness/specs/<spec_id>.py and return it as JSON.

    Spec files define: id, description, constraints, acceptance_criteria,
    target_file, reference_files, language.
    """
    spec_file = _harness_dir(project_root) / "specs" / f"{spec_id}.py"
    if not spec_file.exists():
        return json.dumps({"error": f"Spec not found: {spec_file}"})
    try:
        spec_dict = _load_spec_module(spec_file)
        # Back-compat: also check metadata for target_file / reference_files
        meta = spec_dict.get("metadata", {})
        if not spec_dict.get("target_file") and meta.get("target_file"):
            spec_dict["target_file"] = meta["target_file"]
        if not spec_dict.get("reference_files") and meta.get("reference_files"):
            spec_dict["reference_files"] = meta["reference_files"]
        if not spec_dict.get("language") and meta.get("language"):
            spec_dict["language"] = meta["language"]
        return json.dumps(spec_dict, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to load spec: {e}"})


@mcp.tool()
def context_fetch(reference_files: list[str], target_file: str, project_root: str) -> str:
    """
    Read reference_files and the directory listing adjacent to target_file.
    Returns concatenated file contents, each section prefixed with its path.
    Files larger than 50 KB are truncated.
    """
    root = Path(project_root)
    chunks: list[str] = []
    MAX_BYTES = 50_000

    for ref in reference_files:
        path = Path(ref) if Path(ref).is_absolute() else root / ref
        if path.exists() and path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")
            if len(content) > MAX_BYTES:
                content = content[:MAX_BYTES] + f"\n... [truncated at {MAX_BYTES} bytes]"
            chunks.append(f"=== {ref} ===\n{content}")
        else:
            chunks.append(f"=== {ref} === [NOT FOUND]")

    if target_file:
        target = Path(target_file) if Path(target_file).is_absolute() else root / target_file
        target_dir = target.parent
        if target_dir.exists():
            files = sorted(f.name for f in target_dir.iterdir() if f.is_file())
            chunks.append(f"=== {target_dir.relative_to(root)} (directory) ===\n" + "\n".join(files))

    return "\n\n".join(chunks) if chunks else "No context files found."


@mcp.tool()
def artifact(
    action: str,
    project_root: str,
    run_id: str = "",
    spec_id: str = "",
    implementation: str = "",
    tests: str = "",
    outcome: str = "",
    attempts: int = 0,
    gate_results: list[dict[str, Any]] | None = None,
    notes: str = "",
) -> str:
    """
    CRUD for run artifacts in .harness/results/.

    action="save": persist a run. Required: spec_id, implementation, tests, outcome, attempts, gate_results. Returns run_id.
    action="load": read artifact by run_id. Returns full artifact JSON.
    action="escalate": mark a run as escalated. Required: run_id. Returns "escalated".

    outcome values: 'in_progress' | 'passed' | 'escalated'.
    """
    if action == "save":
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        new_run_id = f"{spec_id}-{ts}"
        results_dir = _harness_dir(project_root) / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "run_id": new_run_id,
            "spec_id": spec_id,
            "outcome": outcome,
            "attempts": attempts,
            "gate_results": gate_results or [],
            "implementation": implementation,
            "tests": tests,
            "notes": notes,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        (results_dir / f"{new_run_id}.json").write_text(json.dumps(data, indent=2))
        return new_run_id
    if action == "load":
        results_dir = _harness_dir(project_root) / "results"
        exact = results_dir / f"{run_id}.json"
        if exact.exists():
            return exact.read_text()
        for f in sorted(results_dir.glob(f"*{run_id}*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            return f.read_text()
        return json.dumps({"error": f"Run not found: {run_id}"})
    if action == "escalate":
        artifact_file = _find_artifact(run_id, project_root)
        if not artifact_file:
            return json.dumps({"error": f"Artifact not found: {run_id}"})
        data = json.loads(artifact_file.read_text())
        data["outcome"] = "escalated"
        artifact_file.write_text(json.dumps(data, indent=2))
        return "escalated"
    return json.dumps({"error": f"Unknown action: {action}. Use save|load|escalate."})


@mcp.tool()
def repair_run(run_id: str, diff: str, language: str, project_root: str) -> str:
    """
    Apply a unified diff to the stored implementation, run gates, and update the artifact.

    The implementation stays server-side — only the diff and gate results travel through
    the context window. On full pass returns {"passed": true, "run_id": ...}.
    On failure returns the failing gate results. On patch error returns {"error": ...,
    "fallback": "rewrite"} so the caller can fall back to a full rewrite.
    """
    artifact_file = _find_artifact(run_id, project_root)
    if not artifact_file:
        return json.dumps({"error": f"Artifact not found: {run_id}"})

    artifact: dict[str, Any] = json.loads(artifact_file.read_text())
    patched, patch_err = _apply_patch(artifact["implementation"], diff)
    if patch_err:
        return json.dumps({"error": patch_err, "fallback": "rewrite"})

    try:
        results = run_suite_for(language, patched, artifact["tests"], project_root)
    except Exception as e:
        return json.dumps({"error": f"Gate execution failed: {e}"})

    artifact["implementation"] = patched
    artifact["attempts"] = artifact.get("attempts", 1) + 1
    artifact["gate_results"] = [r.to_dict() for r in results]

    all_passed = all(r.passed for r in results)
    if all_passed:
        artifact["outcome"] = "passed"
    artifact_file.write_text(json.dumps(artifact, indent=2))

    if all_passed:
        return json.dumps({"passed": True, "run_id": run_id})

    failed = next(r for r in results if not r.passed)
    return json.dumps(failed.to_dict(), indent=2)


@mcp.tool()
def memory(
    action: str,
    project_root: str,
    errors_text: str = "",
    gate: str = "",
    spec_id: str = "",
    attempt: int = 0,
    outcome: str = "",
    limit: int = 3,
) -> str:
    """
    Gate failure memory.

    action="record": save a failure/resolution. Required: spec_id, gate, errors_text, attempt, outcome ('passed'|'escalated').
    action="retrieve": BM25 search for similar past failures. Required: errors_text, gate. Optional: limit (default 3).

    Returns "recorded" or formatted failure narratives.
    """
    try:
        if action == "record":
            _memory(project_root).record(spec_id, gate, errors_text, attempt, outcome)
            return "recorded"
        if action == "retrieve":
            narratives = _memory(project_root).retrieve_similar(errors_text, gate, limit)
            return "\n---\n".join(narratives) if narratives else "No similar past failures found."
        return json.dumps({"error": f"Unknown action: {action}. Use record|retrieve."})
    except Exception as e:
        return f"memory failed: {e}"


@mcp.tool()
def dag_load(task_id: str, project_root: str) -> str:
    """
    Load a task DAG from .harness/tasks/<task_id>.py, validate it (no cycles,
    all deps exist), and return execution layers as JSON.

    Returns: {"task_id": str, "description": str, "layers": [[spec_id, ...], ...]}
    Each layer is a list of spec IDs that can be worked after all previous layers pass.
    """
    task_file = _harness_dir(project_root) / "tasks" / f"{task_id}.py"
    if not task_file.exists():
        return json.dumps({"error": f"Task not found: {task_file}"})
    try:
        task = _load_task_module(task_file)
        resolver = DAGResolver()
        resolver.validate(task)
        layers = resolver.execution_layers(task)
        return json.dumps({
            "task_id": task.id,
            "description": task.description,
            "layers": layers,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def checkpoint(
    action: str,
    task_id: str,
    project_root: str,
    completed: list[str] | None = None,
) -> str:
    """
    Task resume checkpoints.

    action="read": return completed spec IDs for a task. Returns {"task_id": ..., "completed": [...]}.
    action="write": save completed spec IDs. Required: completed list. Returns "checkpoint saved".
    """
    checkpoint_dir = _harness_dir(project_root) / "checkpoints"
    checkpoint_file = checkpoint_dir / f"{task_id}.json"
    if action == "read":
        if not checkpoint_file.exists():
            return json.dumps({"task_id": task_id, "completed": []})
        return checkpoint_file.read_text()
    if action == "write":
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": task_id,
            "completed": completed or [],
            "updated": datetime.now(UTC).isoformat(),
        }
        checkpoint_file.write_text(json.dumps(data, indent=2))
        return "checkpoint saved"
    return json.dumps({"error": f"Unknown action: {action}. Use read|write."})


@mcp.tool()
def harness_status(project_root: str) -> str:
    """
    List recent harness runs from .harness/results/, newest first.
    Shows spec_id, outcome, timestamp, and first failing gate (if escalated).
    """
    results_dir = _harness_dir(project_root) / "results"
    if not results_dir.exists():
        return "No results yet. Run /write-spec <description> to start."

    files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "No results yet."

    lines = []
    for f in files[:20]:
        try:
            data: dict[str, Any] = json.loads(f.read_text())
            outcome = data.get("outcome", "?")
            spec_id = data.get("spec_id", "?")
            ts = data.get("timestamp", "?")[:19].replace("T", " ")
            failed_gate = ""
            for gr in data.get("gate_results", []):
                if not gr.get("passed"):
                    failed_gate = f" [failed: {gr['gate']}]"
                    break
            symbol = "✓" if outcome == "passed" else "⚠"
            lines.append(f"{symbol} {spec_id}  {outcome}{failed_gate}  {ts}")
        except Exception:
            lines.append(f"? {f.name} [unreadable]")

    return "\n".join(lines)


@mcp.tool()
def doctor(project_root: str = "") -> str:
    """
    Diagnose gate-tool readiness for a project (ticket 0022).

    Scans `project_root` (default: the current working directory) for language
    manifests, then probes each detected language's required gate tools with
    `<tool> --version` under a 5-second timeout. Never modifies the project or
    installs anything.

    Returns JSON `{"output": str, "any_missing": bool}` — `output` is the
    human-readable per-language table; `any_missing` is True when any required
    tool is missing or timed out, so the caller can signal non-zero status for
    CI preflight. On an invalid `project_root` (not a directory, or outside the
    allowed root) returns `{"error": str}` before any probe runs.
    """
    try:
        report = run_doctor(project_root)
    except DoctorError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"output": format_report(report), "any_missing": report.any_missing})


if __name__ == "__main__":
    mcp.run()

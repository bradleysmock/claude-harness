"""
harness-no-api-key MCP server.
Provides mechanical tools — gates, files, memory, DAG — for Claude to use as orchestrator.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import types
from datetime import datetime, UTC
from pathlib import Path

# Ensure this directory is on the path so local modules resolve.
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

from gates import run_suite_for
from memory import SQLiteFailureMemory
from dag import DAGResolver
from models import Spec, Task, TaskSpec, GateError

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


def _load_spec_module(path: Path) -> dict:
    """Exec a spec file with a fake harness module injected."""
    harness_mod = types.ModuleType("harness")
    harness_mod.Spec = Spec  # type: ignore[attr-defined]
    sys.modules["harness"] = harness_mod
    try:
        namespace: dict = {}
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
        namespace: dict = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        task = namespace.get("task")
        if not isinstance(task, Task):
            raise ValueError("Task file did not define a 'task' variable of type Task")
        return task
    finally:
        sys.modules.pop("harness", None)


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def gate_run(implementation: str, tests: str, language: str, project_root: str) -> str:
    """
    Write implementation and tests to a temp directory and run the full gate suite.
    Returns JSON list of gate results, stopping at first failure (fail-fast).

    Each result has: gate, passed, errors (list of {message, file, line, column, code, severity}), duration_ms.
    """
    try:
        results = run_suite_for(language, implementation, tests, project_root)
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
def artifact_save(
    spec_id: str,
    implementation: str,
    tests: str,
    outcome: str,
    attempts: int,
    gate_results: list[dict],
    project_root: str,
    notes: str = "",
) -> str:
    """
    Save a completed run to .harness/results/<spec_id>-<timestamp>.json.
    Returns the run_id for use with artifact_load and /harness:finish.
    outcome: 'in_progress' | 'passed' | 'escalated'.
    """
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_id = f"{spec_id}-{ts}"
    results_dir = _harness_dir(project_root) / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    artifact = {
        "run_id": run_id,
        "spec_id": spec_id,
        "outcome": outcome,
        "attempts": attempts,
        "gate_results": gate_results,
        "implementation": implementation,
        "tests": tests,
        "notes": notes,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (results_dir / f"{run_id}.json").write_text(json.dumps(artifact, indent=2))
    return run_id


@mcp.tool()
def artifact_load(run_id: str, project_root: str) -> str:
    """Load a result file by run_id. Returns the full artifact as JSON."""
    results_dir = _harness_dir(project_root) / "results"
    exact = results_dir / f"{run_id}.json"
    if exact.exists():
        return exact.read_text()
    for f in sorted(results_dir.glob(f"*{run_id}*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        return f.read_text()
    return json.dumps({"error": f"Run not found: {run_id}"})


@mcp.tool()
def memory_record(
    spec_id: str,
    gate: str,
    errors_text: str,
    attempt: int,
    outcome: str,
    project_root: str,
) -> str:
    """
    Record a gate failure or pass to the failure memory database.
    errors_text: concatenated error messages from the failing gate.
    outcome: 'passed' | 'escalated'.
    """
    try:
        _memory(project_root).record(spec_id, gate, errors_text, attempt, outcome)
        return "recorded"
    except Exception as e:
        return f"memory_record failed: {e}"


@mcp.tool()
def memory_retrieve(errors_text: str, gate: str, project_root: str, limit: int = 3) -> str:
    """
    BM25 keyword search over past failures matching the same gate.
    Returns formatted narratives of similar failures, or empty string if none found.
    """
    try:
        narratives = _memory(project_root).retrieve_similar(errors_text, gate, limit)
        if not narratives:
            return "No similar past failures found."
        return "\n---\n".join(narratives)
    except Exception as e:
        return f"memory_retrieve failed: {e}"


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
def checkpoint_read(task_id: str, project_root: str) -> str:
    """
    Read checkpoint for a task. Returns JSON with 'completed' list of spec IDs
    that have already passed, so /harness:task can skip them on resume.
    """
    checkpoint_file = _harness_dir(project_root) / "checkpoints" / f"{task_id}.json"
    if not checkpoint_file.exists():
        return json.dumps({"task_id": task_id, "completed": []})
    return checkpoint_file.read_text()


@mcp.tool()
def checkpoint_write(task_id: str, completed: list[str], project_root: str) -> str:
    """
    Write checkpoint for a task. completed is the list of spec IDs that have passed.
    Call after each spec passes so the task can resume after interruption.
    """
    checkpoint_dir = _harness_dir(project_root) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "task_id": task_id,
        "completed": completed,
        "updated": datetime.now(UTC).isoformat(),
    }
    (checkpoint_dir / f"{task_id}.json").write_text(json.dumps(data, indent=2))
    return "checkpoint saved"


@mcp.tool()
def harness_status(project_root: str) -> str:
    """
    List recent harness runs from .harness/results/, newest first.
    Shows spec_id, outcome, timestamp, and first failing gate (if escalated).
    """
    results_dir = _harness_dir(project_root) / "results"
    if not results_dir.exists():
        return "No results yet. Run /harness:submit <spec-id> to start."

    files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "No results yet."

    lines = []
    for f in files[:20]:
        try:
            data = json.loads(f.read_text())
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
def repair_run(run_id: str, diff: str, language: str, project_root: str) -> str:
    """
    Apply a unified diff to the stored implementation, run gates, and update the artifact.

    The implementation stays server-side — only the diff and gate results travel through
    the context window. On full pass returns {"passed": true, "run_id": ...}.
    On failure returns the failing gate results. On patch error returns {"error": ...,
    "fallback": "rewrite"} so the caller can fall back to a full rewrite for this attempt.
    """
    artifact_file = _find_artifact(run_id, project_root)
    if not artifact_file:
        return json.dumps({"error": f"Artifact not found: {run_id}"})

    artifact = json.loads(artifact_file.read_text())
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
def artifact_escalate(run_id: str, project_root: str) -> str:
    """Mark an in-progress artifact as escalated after all repair attempts are exhausted."""
    artifact_file = _find_artifact(run_id, project_root)
    if not artifact_file:
        return json.dumps({"error": f"Artifact not found: {run_id}"})
    artifact = json.loads(artifact_file.read_text())
    artifact["outcome"] = "escalated"
    artifact_file.write_text(json.dumps(artifact, indent=2))
    return "escalated"


if __name__ == "__main__":
    mcp.run()

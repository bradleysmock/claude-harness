#!/usr/bin/env python3
"""MCP server wrapping the harness-full LLM coding harness CLI.

Prerequisites: run setup.sh once to create the venv and install dependencies.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "harness",
    instructions=(
        "Tools for the harness-full LLM coding harness. "
        "Typical workflow: harness_score → harness_harden → harness_submit. "
        "For multi-spec features: harness_task. "
        "On escalation: harness_debug, fix the spec, resubmit. "
        "Use slash commands /forge-spec, /forge-task, /finish-task, /debug-escalation "
        "for the exploration and delivery steps."
    ),
)


def _run(args: list[str], cwd: str | None = None, timeout: int = 300) -> str:
    # Prepend this venv's bin so gate tools (ruff, mypy, bandit, pytest, …)
    # installed here are found by harness subprocesses even without activation.
    venv_bin = str(Path(sys.executable).parent)
    env = {**os.environ, "PATH": f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "harness", *args],
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s: harness {' '.join(args)}"

    parts: list[str] = []
    if result.stdout.strip():
        parts.append(result.stdout.strip())
    if result.stderr.strip():
        parts.append(f"stderr:\n{result.stderr.strip()}")
    if not parts:
        parts.append("(no output)")
    if result.returncode not in (0, 1):  # 1 = escalated, not an error
        parts.append(f"exit {result.returncode}")
    return "\n\n".join(parts)


@mcp.tool()
def harness_init(project_root: str = ".") -> str:
    """Initialize the harness in a project directory.
    Creates .harness/ config, databases, and installs .claude/commands/."""
    return _run(["init"], cwd=project_root, timeout=30)


@mcp.tool()
def harness_score(spec_id: str, project_root: str = ".") -> str:
    """Score a spec's quality before submission.
    Returns per-dimension scores and a pass/warn/block verdict.

    spec_id: stem of the spec file under .harness/specs/ (e.g. 'user-email-validation')
    """
    return _run(["score", spec_id], cwd=project_root, timeout=60)


@mcp.tool()
def harness_harden(spec_id: str, project_root: str = ".") -> str:
    """Preview spec hardening: pin identifiers, surface open ambiguities, add type signatures.
    Does not modify the spec file; use output to refine manually before submitting.

    spec_id: stem of the spec file under .harness/specs/
    """
    return _run(["harden", spec_id], cwd=project_root, timeout=120)


@mcp.tool()
def harness_submit(spec_id: str, project_root: str = ".") -> str:
    """Submit a spec through the full generation → gates → repair loop.
    Returns outcome (passed or escalated) and per-gate results.

    spec_id: stem of the spec file under .harness/specs/
    """
    return _run(["submit", spec_id], cwd=project_root, timeout=600)


@mcp.tool()
def harness_task(task_file: str, project_root: str = ".") -> str:
    """Execute a multi-spec task DAG with dependency ordering and concurrent execution.
    Specs in the same layer run in parallel. Returns per-spec outcomes and overall result.

    task_file: path to the task file or its stem under .harness/tasks/
    """
    return _run(["task", task_file], cwd=project_root, timeout=3600)


@mcp.tool()
def harness_task_reset(task_name: str, project_root: str = ".") -> str:
    """Clear a task's checkpoint so the next harness_task call re-runs all specs from scratch.

    task_name: task name as shown by harness_status
    """
    return _run(["task-reset", task_name], cwd=project_root, timeout=30)


@mcp.tool()
def harness_debug(run_id: str, project_root: str = ".") -> str:
    """Classify failure mode and propose spec corrections for an escalated run.
    Use /debug-escalation for a more interactive diagnosis workflow.

    run_id: run ID as shown by harness_status
    """
    return _run(["debug", run_id], cwd=project_root, timeout=120)


@mcp.tool()
def harness_status(project_root: str = ".") -> str:
    """Show recent harness runs: spec IDs, outcomes, gate results, timestamps."""
    return _run(["status"], cwd=project_root, timeout=30)


@mcp.tool()
def harness_stats(project_root: str = ".") -> str:
    """Show memory statistics: resolution rates, failure counts by gate, mean attempts to resolve."""
    return _run(["stats"], cwd=project_root, timeout=30)


@mcp.tool()
def harness_checkpoint_status(task_name: str, project_root: str = ".") -> str:
    """Show checkpoint state for a task: completed specs, pending specs, blocked specs.

    task_name: task name as shown by harness_status
    """
    return _run(["checkpoint-status", task_name], cwd=project_root, timeout=30)


@mcp.tool()
def harness_index_status(project_root: str = ".") -> str:
    """Show the state of the semantic codebase index: file count, last sync, index size."""
    return _run(["index-status"], cwd=project_root, timeout=30)


@mcp.tool()
def harness_index_rebuild(project_root: str = ".") -> str:
    """Rebuild the semantic codebase index from scratch.
    Use when files were added or removed outside a normal harness workflow."""
    return _run(["index-rebuild"], cwd=project_root, timeout=300)


@mcp.tool()
def harness_sandbox_build(project_root: str = ".") -> str:
    """Build the Docker sandbox image for isolated gate execution."""
    return _run(["sandbox-build"], cwd=project_root, timeout=600)


@mcp.tool()
def harness_sandbox_status(project_root: str = ".") -> str:
    """Check whether the Docker sandbox image is built and ready."""
    return _run(["sandbox-status"], cwd=project_root, timeout=30)


if __name__ == "__main__":
    mcp.run()

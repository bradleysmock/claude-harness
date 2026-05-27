#!/usr/bin/env python3
"""PostToolUse hook: per-file linter/SAST run after Write/Edit.

Polyglot — dispatches on file extension. Each gate is skipped if its tool is
not on PATH. Findings are surfaced back to the model via stderr (exit 2) so
the model self-corrects in the same conversation.

Per-file checks only. Project-wide checks (full type-check, full test suite)
belong in the Stop hook.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

TIMEOUT_SECONDS = 20


def extracted_path(tool_name: str, tool_input: dict) -> str | None:
    if tool_name in {"Write", "Edit", "MultiEdit"}:
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str):
            return file_path
    return None


def run_tool(executable: str, args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(cwd) if cwd else None,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, f"{executable} timed out after {TIMEOUT_SECONDS}s"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


# --- Per-language gate runners --------------------------------------------

def gate_python(file_path: str) -> list[str]:
    findings: list[str] = []
    if shutil.which("ruff") is not None:
        return_code, output = run_tool("ruff", ["check", "--output-format", "concise", "--quiet", file_path])
        if return_code not in (0, None) and output.strip():
            findings.append(f"ruff:\n{output.strip()}")
    if shutil.which("bandit") is not None:
        return_code, output = run_tool("bandit", ["-ll", "-q", "-f", "txt", file_path])
        if return_code not in (0, None) and "No issues identified" not in output and output.strip():
            findings.append(f"bandit:\n{output.strip()}")
    return findings


def gate_javascript_typescript(file_path: str) -> list[str]:
    findings: list[str] = []
    if shutil.which("eslint") is not None:
        return_code, output = run_tool("eslint", ["--no-color", "--format", "compact", file_path])
        if return_code not in (0, None) and output.strip():
            findings.append(f"eslint:\n{output.strip()}")
    return findings


def gate_go(file_path: str) -> list[str]:
    findings: list[str] = []
    if shutil.which("gofmt") is not None:
        return_code, output = run_tool("gofmt", ["-l", file_path])
        if return_code not in (0, None) or output.strip():
            if output.strip():
                findings.append(f"gofmt (unformatted):\n{output.strip()}\nRun: gofmt -w {file_path}")
    # `go vet` requires a package context — skip per-file. Defer to stop hook.
    return findings


def gate_rust(file_path: str) -> list[str]:
    findings: list[str] = []
    if shutil.which("rustfmt") is not None:
        return_code, output = run_tool("rustfmt", ["--check", "--edition", "2021", file_path])
        if return_code not in (0, None) and output.strip():
            findings.append(f"rustfmt (formatting drift):\n{output.strip()[:600]}")
    # `cargo clippy` requires crate context — skip per-file. Defer to stop hook.
    return findings


GATE_DISPATCH: dict[tuple[str, ...], Callable[[str], list[str]]] = {
    (".py", ".pyi"): gate_python,
    (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"): gate_javascript_typescript,
    (".go",): gate_go,
    (".rs",): gate_rust,
}


def dispatch_gate(file_path: str) -> list[str]:
    ext = Path(file_path).suffix.lower()
    for extensions, runner in GATE_DISPATCH.items():
        if ext in extensions:
            return runner(file_path)
    return []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    file_path = extracted_path(tool_name, tool_input)
    if file_path is None:
        return 0
    if not Path(file_path).is_file():
        return 0

    findings = dispatch_gate(file_path)
    if not findings:
        return 0

    feedback = (
        f"post_write_gate findings on {Path(file_path).name} — address before continuing:\n\n"
        + "\n\n".join(findings)
    )
    sys.stderr.write(feedback + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models import GateError, GateResult
from gates import ProcessResult


_CARGO_TOML = """\
[package]
name = "harness-temp"
version = "0.1.0"
edition = "2021"

[lib]
name = "harness_temp"
path = "src/lib.rs"

[dev-dependencies]
"""


@dataclass
class RustEnv:
    root: Path
    lib_file: Path


def _find_rust_crate(project_root: str) -> Path | None:
    """Find the Rust crate directory: project_root itself, or first subdir with Cargo.toml."""
    root = Path(project_root)
    if (root / "Cargo.toml").exists():
        return root
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "Cargo.toml").exists():
            return child
    return None


def _parse_multi_file(implementation: str) -> dict[str, str] | None:
    """
    If implementation contains '// FILE: <path>' markers, parse it into a dict
    mapping relative file paths to their contents.  Returns None for single-file mode.
    """
    import re
    marker = re.compile(r'^// FILE: (.+)$', re.MULTILINE)
    splits = marker.split(implementation)
    if len(splits) < 3:
        return None
    # splits = [preamble, path1, content1, path2, content2, ...]
    files: dict[str, str] = {}
    it = iter(splits[1:])
    for path in it:
        content = next(it, "")
        files[path.strip()] = content.strip()
    return files if files else None


def _make_env(implementation: str, tests: str, project_root: str) -> RustEnv:
    crate_dir = _find_rust_crate(project_root)
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_rs_"))

    multi = _parse_multi_file(implementation)

    if crate_dir is not None:
        # Copy the real crate to temp dir so all deps and source files are available.
        shutil.copytree(str(crate_dir), str(tmpdir), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("target", ".git"))
        src = tmpdir / "src"
        src.mkdir(exist_ok=True)

        if multi:
            # Multi-file mode: write each file relative to crate_dir
            for rel_path, content in multi.items():
                # Strip leading "api/" or other crate-dir prefix if present
                rel = Path(rel_path)
                crate_name = crate_dir.name  # e.g. "api"
                parts = rel.parts
                if parts and parts[0] == crate_name:
                    rel = Path(*parts[1:])
                dest = tmpdir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Append tests to the last written file (target file) if tests exist
                final = content
                if rel_path == list(multi.keys())[-1]:
                    tests_stripped = tests.strip()
                    if tests_stripped and tests_stripped not in final:
                        if "#[cfg(test)]" not in final:
                            final += f"\n\n{tests_stripped}"
                dest.write_text(final, encoding="utf-8")
            lib = tmpdir / "src" / "lib.rs"  # placeholder; not directly used
        else:
            # Single-file mode: write implementation to a new module in routes/
            routes_dir = src / "routes"
            if routes_dir.is_dir():
                lib = routes_dir / "harness_impl.rs"
            else:
                lib = src / "harness_impl.rs"
            combined = implementation
            tests_stripped = tests.strip()
            if tests_stripped and tests_stripped not in combined:
                if "#[cfg(test)]" not in combined:
                    combined += f"\n\n{tests_stripped}"
            lib.write_text(combined, encoding="utf-8")
            # Expose the new module
            routes_mod = routes_dir / "mod.rs" if routes_dir.is_dir() else None
            if routes_mod and routes_mod.exists():
                content = routes_mod.read_text(encoding="utf-8")
                if "harness_impl" not in content:
                    routes_mod.write_text(
                        "pub mod harness_impl;\n" + content, encoding="utf-8"
                    )
            else:
                for entry in ["src/lib.rs", "src/main.rs"]:
                    entry_path = tmpdir / entry
                    if entry_path.exists():
                        content = entry_path.read_text(encoding="utf-8")
                        if "harness_impl" not in content:
                            entry_path.write_text(
                                "pub mod harness_impl;\n" + content, encoding="utf-8"
                            )
                        break
    else:
        # Fallback: minimal standalone crate (no real project found)
        (tmpdir / "Cargo.toml").write_text(_CARGO_TOML)
        src = tmpdir / "src"
        src.mkdir()
        lib = src / "lib.rs"
        combined = implementation if not multi else "\n".join(multi.values())
        tests_stripped = tests.strip()
        if tests_stripped and tests_stripped not in combined:
            if "#[cfg(test)]" not in combined:
                combined += f"\n\n{tests_stripped}"
        lib.write_text(combined, encoding="utf-8")

    return RustEnv(root=tmpdir, lib_file=tmpdir / "src" / "lib.rs")


def _exec(command: list[str], env: RustEnv, timeout: int = 120) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(env.root), timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _timeout_error(gate: str) -> GateResult:
    return GateResult(
        gate=gate, passed=False,
        errors=[GateError(message="Timed out", file=None, line=None, column=None,
                          code="TIMEOUT", severity="error")],
        duration_ms=120000,
    )


def _parse_cargo_json(stdout: str) -> list[GateError]:
    errors = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("reason") != "compiler-message":
            continue
        msg: dict[str, Any] = obj.get("message", {})
        level = msg.get("level", "")
        if level not in ("error", "warning"):
            continue
        spans: list[Any] = msg.get("spans", [])
        primary = next((s for s in spans if s.get("is_primary")), spans[0] if spans else None)
        errors.append(GateError(
            message=msg.get("message", ""),
            file=primary["file_name"] if primary else None,
            line=primary["line_start"] if primary else None,
            column=primary["column_start"] if primary else None,
            code=msg.get("code", {}).get("code") if msg.get("code") else None,
            severity=level,
        ))
    return errors


def _check_gate(env: RustEnv) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(["cargo", "check", "--message-format=json", "--quiet"], env)
    except subprocess.TimeoutExpired:
        return _timeout_error("check")
    errors = _parse_cargo_json(result.stdout)
    return GateResult(gate="check", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _clippy_gate(env: RustEnv) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(
            ["cargo", "clippy", "--message-format=json", "--quiet", "--", "-D", "warnings"], env
        )
    except subprocess.TimeoutExpired:
        return _timeout_error("clippy")
    errors = _parse_cargo_json(result.stdout)
    return GateResult(gate="clippy", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _test_gate(env: RustEnv) -> GateResult:
    start = time.monotonic()
    try:
        result = _exec(["cargo", "test", "--", "--nocapture"], env, timeout=180)
    except subprocess.TimeoutExpired:
        return _timeout_error("test")
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    for line in result.output.splitlines():
        if "FAILED" in line and "test " in line:
            test_name = line.strip().split()[1] if len(line.split()) > 1 else line
            errors.append(GateError(
                message=f"Test failed: {test_name}",
                file="src/lib.rs", line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))
        elif "panicked at" in line and errors:
            last = errors[-1]
            errors[-1] = GateError(
                message=f"{last.message} — {line.strip()}",
                file=last.file, line=last.line, column=last.column,
                code=last.code, severity=last.severity,
            )
    if not errors:
        errors.append(GateError(
            message=result.output[:600], file="src/lib.rs",
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def _audit_gate(env: RustEnv) -> GateResult:
    import shutil as _shutil
    if not _shutil.which("cargo-audit"):
        return GateResult(gate="audit", passed=True, errors=[], duration_ms=0)
    start = time.monotonic()
    try:
        result = _exec(["cargo", "audit", "--json"], env)
    except subprocess.TimeoutExpired:
        return _timeout_error("audit")
    errors = []
    try:
        report: dict[str, Any] = json.loads(result.stdout)
        for vuln in report.get("vulnerabilities", {}).get("list", []):
            adv = vuln.get("advisory", {})
            pkg = vuln.get("package", {})
            errors.append(GateError(
                message=(f"{pkg.get('name', '?')} {pkg.get('version', '?')}: "
                         f"{adv.get('title', 'vulnerability')} ({adv.get('id', '')})"),
                file="Cargo.toml", line=None, column=None,
                code=adv.get("id"), severity="error",
            ))
    except json.JSONDecodeError:
        pass
    return GateResult(gate="audit", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def run_rust_suite(implementation: str, tests: str, project_root: str) -> list[GateResult]:
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_check_gate, _clippy_gate, _test_gate, _audit_gate]:
            result = gate_fn(env)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results

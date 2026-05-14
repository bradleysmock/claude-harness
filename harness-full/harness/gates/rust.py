"""
Rust gate suite.

Gates (in order):
  1. check    cargo check --message-format=json   fast compile check (no codegen)
  2. clippy   cargo clippy --message-format=json   lints + idiom corrections
  3. test     cargo test                           unit + integration tests
  4. audit    cargo audit                          dependency vulnerability scan (optional)

Tool requirements
─────────────────
Required:  cargo, rustc   (https://rustup.rs/)
Optional:  cargo-audit    (cargo install cargo-audit)
           audit gate is skipped gracefully if not installed.

Execution environment
─────────────────────
A minimal Cargo library project is created in the temp directory:

  tmpdir/
  ├── Cargo.toml
  └── src/
      └── lib.rs      ← implementation + inline tests

The generated implementation should be a library crate (no `fn main`).
Tests are written as a `#[cfg(test)] mod tests { ... }` block inside
lib.rs, or the LLM may place them in the implementation directly.

Rust's structured JSON diagnostic output (--message-format=json) makes
error parsing significantly more reliable than regex over human-readable
compiler output.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..models import GateError, GateResult, GeneratedArtifact
from .base import BaseGate, ProcessResult, run_process, require_tool


# ── Execution environment ─────────────────────────────────────────────────────

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

    @classmethod
    @contextmanager
    def create(cls, artifact: GeneratedArtifact, project_root: str):
        require_tool("cargo", hint="https://rustup.rs/")
        tmpdir = Path(tempfile.mkdtemp(prefix="harness_rs_"))
        try:
            (tmpdir / "Cargo.toml").write_text(_CARGO_TOML)
            src = tmpdir / "src"
            src.mkdir()

            lib = src / "lib.rs"

            # Combine implementation and tests into lib.rs.
            # If the LLM put tests in a separate block, merge them.
            combined = artifact.implementation
            tests = artifact.tests.strip()
            if tests and tests not in combined:
                # Append tests if not already embedded
                if "#[cfg(test)]" not in combined:
                    combined += f"\n\n{tests}"
            lib.write_text(combined, encoding="utf-8")

            yield cls(root=tmpdir, lib_file=lib)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── JSON diagnostic parser ────────────────────────────────────────────────────

def _parse_cargo_json(output: str, env: RustEnv) -> list[GateError]:
    """
    Parse cargo's --message-format=json output.
    Each line is a JSON object with a 'reason' field.
    We extract 'compiler-message' entries with level 'error' or 'warning'.
    """
    errors: list[GateError] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("reason") != "compiler-message":
            continue

        msg = obj.get("message", {})
        level = msg.get("level", "")
        if level not in ("error", "warning"):
            continue

        # Extract primary span
        spans = msg.get("spans", [])
        primary = next((s for s in spans if s.get("is_primary")), spans[0] if spans else None)

        file_name = primary["file_name"] if primary else None
        line_num = primary["line_start"] if primary else None
        col_num = primary["column_start"] if primary else None

        errors.append(GateError(
            message=msg.get("message", ""),
            file=file_name,
            line=line_num,
            column=col_num,
            code=msg.get("code", {}).get("code") if msg.get("code") else None,
            severity=level,
        ))

    return errors


# ── Gate 1: Check (fast compile) ──────────────────────────────────────────────

class RustCheckGate(BaseGate):
    gate_name = "check"
    DEFAULT_TIMEOUT = 60

    def _command(self, env: RustEnv) -> list[str]:
        return ["cargo", "check", "--message-format=json", "--quiet"]

    def _parse_errors(self, result: ProcessResult, env: RustEnv) -> list[GateError]:
        return _parse_cargo_json(result.stdout, env)


# ── Gate 2: Clippy (lints) ────────────────────────────────────────────────────

class RustClippyGate(BaseGate):
    gate_name = "clippy"
    DEFAULT_TIMEOUT = 60

    def _command(self, env: RustEnv) -> list[str]:
        return [
            "cargo", "clippy",
            "--message-format=json",
            "--quiet",
            "--",
            "-D", "warnings",   # treat warnings as errors
        ]

    def _parse_errors(self, result: ProcessResult, env: RustEnv) -> list[GateError]:
        return _parse_cargo_json(result.stdout, env)


# ── Gate 3: Tests ─────────────────────────────────────────────────────────────

class RustTestGate(BaseGate):
    gate_name = "test"
    DEFAULT_TIMEOUT = 120

    def _command(self, env: RustEnv) -> list[str]:
        return ["cargo", "test", "--", "--nocapture"]

    def _parse_errors(self, result: ProcessResult, env: RustEnv) -> list[GateError]:
        if result.returncode == 0:
            return []

        errors: list[GateError] = []
        current_test: str | None = None

        for line in result.output.splitlines():
            # test test_name ... FAILED
            if "FAILED" in line and "test " in line:
                current_test = line.strip().split()[1] if len(line.split()) > 1 else line
                errors.append(GateError(
                    message=f"Test failed: {current_test}",
                    file="src/lib.rs",
                    line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            # thread 'test_name' panicked at 'message', src/lib.rs:42
            elif "panicked at" in line:
                # Annotate the last error with panic detail
                if errors:
                    errors[-1] = GateError(
                        message=errors[-1].message + f" — {line.strip()}",
                        file=errors[-1].file,
                        line=errors[-1].line,
                        column=errors[-1].column,
                        code=errors[-1].code,
                        severity=errors[-1].severity,
                    )

        if not errors:
            errors.append(GateError(
                message=result.output[:600],
                file="src/lib.rs",
                line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))
        return errors


# ── Gate 4: Audit (optional) ──────────────────────────────────────────────────

class RustAuditGate(BaseGate):
    gate_name = "audit"
    DEFAULT_TIMEOUT = 30

    def _command(self, env: RustEnv) -> list[str]:
        return ["cargo", "audit", "--json"]

    def run(self, artifact: GeneratedArtifact, env: RustEnv) -> GateResult:
        import shutil as _shutil
        if not _shutil.which("cargo-audit"):
            return GateResult(
                gate=self.gate_name, passed=True, errors=[], duration_ms=0,
            )
        return super().run(artifact, env)

    def _parse_errors(self, result: ProcessResult, env: RustEnv) -> list[GateError]:
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        errors = []
        for vuln in report.get("vulnerabilities", {}).get("list", []):
            adv = vuln.get("advisory", {})
            pkg = vuln.get("package", {})
            errors.append(GateError(
                message=(
                    f"{pkg.get('name', '?')} {pkg.get('version', '?')}: "
                    f"{adv.get('title', 'vulnerability')} ({adv.get('id', '')})"
                ),
                file="Cargo.toml",
                line=None, column=None,
                code=adv.get("id"),
                severity="error",
            ))
        return errors


# ── Suite ─────────────────────────────────────────────────────────────────────

class RustGate:
    """Binds a BaseGate to a RustEnv. Satisfies ExecutionAdapter."""

    def __init__(self, inner: BaseGate, env: RustEnv):
        self._inner = inner
        self._env = env

    @property
    def gate_name(self) -> str:
        return self._inner.gate_name

    def run(self, artifact: GeneratedArtifact) -> GateResult:
        return self._inner.run(artifact, self._env)


def rust_gate_classes() -> list[BaseGate]:
    """Ordered cheapest → most expensive."""
    return [RustCheckGate(), RustClippyGate(), RustTestGate(), RustAuditGate()]

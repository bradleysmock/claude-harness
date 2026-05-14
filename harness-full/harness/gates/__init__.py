"""
Gate suite registry.

Exports all language adapters and a gate_suite_for() context manager
that yields ready-to-use ExecutionAdapters for a given language.

Supported languages
───────────────────
python     mypy + ruff + bandit + pytest     always available
typescript tsc + eslint + jest               requires Node.js / npm
go         build + vet + staticcheck + test  requires Go toolchain
rust       check + clippy + test + audit     requires Rust/Cargo
"""

from __future__ import annotations
from contextlib import contextmanager
from typing import Literal

from ..models import GeneratedArtifact, GateResult

# ── Python ────────────────────────────────────────────────────────────────────
from .python import (
    ExecutionEnvironment,
    SyntaxGate, TypeCheckGate, LintGate, TestGate, SecurityGate,
    PythonGate,
    default_python_gate_classes,
)

# ── TypeScript ────────────────────────────────────────────────────────────────
from .typescript import (
    TypeScriptEnv,
    TypeScriptTypeCheckGate, TypeScriptLintGate, TypeScriptTestGate,
    TypeScriptGate,
    typescript_gate_classes,
)

# ── Go ────────────────────────────────────────────────────────────────────────
from .go import (
    GoEnv,
    GoBuildGate, GoVetGate, GoStaticcheckGate, GoTestGate,
    GoGate,
    go_gate_classes,
)

# ── Rust ──────────────────────────────────────────────────────────────────────
from .rust import (
    RustEnv,
    RustCheckGate, RustClippyGate, RustTestGate, RustAuditGate,
    RustGate,
    rust_gate_classes,
)

Language = Literal["python", "typescript", "go", "rust"]


@contextmanager
def gate_suite_for(
    language: Language,
    artifact: GeneratedArtifact,
    project_root: str,
):
    """
    Context manager yielding ready-to-use ExecutionAdapters for the given language.

    with gate_suite_for("rust", artifact, "./") as gates:
        results = [g.run(artifact) for g in gates]
    """
    if language == "python":
        with ExecutionEnvironment.create(artifact, project_root) as env:
            yield [PythonGate(g, env) for g in default_python_gate_classes()]
    elif language == "typescript":
        with TypeScriptEnv.create(artifact, project_root) as env:
            yield [TypeScriptGate(g, env) for g in typescript_gate_classes()]
    elif language == "go":
        with GoEnv.create(artifact, project_root) as env:
            yield [GoGate(g, env) for g in go_gate_classes()]
    elif language == "rust":
        with RustEnv.create(artifact, project_root) as env:
            yield [RustGate(g, env) for g in rust_gate_classes()]
    else:
        raise ValueError(f"Unknown language: '{language}'. Supported: python, typescript, go, rust")


__all__ = [
    "ExecutionEnvironment", "PythonGate", "default_python_gate_classes",
    "SyntaxGate", "TypeCheckGate", "LintGate", "TestGate", "SecurityGate",
    "TypeScriptEnv", "TypeScriptGate", "typescript_gate_classes",
    "TypeScriptTypeCheckGate", "TypeScriptLintGate", "TypeScriptTestGate",
    "GoEnv", "GoGate", "go_gate_classes",
    "GoBuildGate", "GoVetGate", "GoStaticcheckGate", "GoTestGate",
    "RustEnv", "RustGate", "rust_gate_classes",
    "RustCheckGate", "RustClippyGate", "RustTestGate", "RustAuditGate",
    "gate_suite_for", "Language",
]

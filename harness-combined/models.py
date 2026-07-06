from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StackName(StrEnum):
    """Canonical vocabulary for the language stacks the gate engine supports.

    A ``StrEnum`` so each member compares equal to — and hashes like — its plain
    string value (``StackName.PYTHON == "python"``). That keeps it a drop-in for
    the existing ``language: str`` gate dispatch: ``run_suite_on_dir(StackName.X)``
    and ``run_suite_on_dir("x")`` behave identically, and a set of members is
    interchangeable with a set of the equivalent strings. Declaration order is the
    canonical ordering used when reporting detected stacks.
    """

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"


@dataclass
class GateError:
    message: str
    file: str | None
    line: int | None
    column: int | None
    code: str | None
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "code": self.code,
            "severity": self.severity,
        }


@dataclass
class GateResult:
    gate: str
    passed: bool
    errors: list[GateError]
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "passed": self.passed,
            "errors": [e.to_dict() for e in self.errors],
            "duration_ms": self.duration_ms,
        }


@dataclass
class LanguageResult:
    """A single language's gate results, tagged with the stack that produced them.

    The polyglot aggregation layer builds one of these per detected stack so the
    findings formatter can label each section by language without threading the
    stack name alongside a bare ``list[GateResult]``.
    """

    language: StackName
    results: list[GateResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            # ``str(...)`` yields the plain value ("python"), never the enum repr.
            "language": str(self.language),
            "results": [r.to_dict() for r in self.results],
        }


@dataclass
class Spec:
    id: str
    description: str
    constraints: list[str]
    acceptance_criteria: list[str]
    target_file: str = ""
    reference_files: list[str] = field(default_factory=list)
    language: str = "python"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "constraints": self.constraints,
            "acceptance_criteria": self.acceptance_criteria,
            "target_file": self.target_file,
            "reference_files": self.reference_files,
            "language": self.language,
            "metadata": self.metadata,
        }


@dataclass
class TaskSpec:
    spec_id: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    description: str
    specs: list[TaskSpec]

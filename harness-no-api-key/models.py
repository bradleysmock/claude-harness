from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


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

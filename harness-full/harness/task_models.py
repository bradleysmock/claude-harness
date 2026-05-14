"""
Data models for multi-spec task execution.
A Task is a DAG of Specs; a TaskRun is its full audit trail.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from .models import Spec, HarnessRun


@dataclass
class TaskSpec:
    """One node in the task dependency graph."""
    spec: Spec
    depends_on: list[str] = field(default_factory=list)   # spec ids


@dataclass
class Task:
    """A directed acyclic graph of specs representing one feature."""
    id: str
    description: str
    specs: list[TaskSpec]

    def spec_by_id(self, spec_id: str) -> TaskSpec | None:
        return next((s for s in self.specs if s.spec.id == spec_id), None)


@dataclass
class SpecRun:
    """Result of one spec within a task execution."""
    task_spec: TaskSpec
    run: HarnessRun
    blocked_by: str | None = None   # upstream spec id that failed


@dataclass
class TaskRun:
    """Complete audit trail for a task execution."""
    id: str
    task: Task
    spec_runs: list[SpecRun]
    outcome: Literal["passed", "partial", "failed"]
    total_duration_ms: int = 0

    @property
    def passed_specs(self) -> list[SpecRun]:
        return [r for r in self.spec_runs if r.run.outcome == "passed"]

    @property
    def failed_specs(self) -> list[SpecRun]:
        return [r for r in self.spec_runs
                if r.run.outcome != "passed" and not r.blocked_by]

    @property
    def blocked_specs(self) -> list[SpecRun]:
        return [r for r in self.spec_runs if r.blocked_by]

"""
Task checkpointing.

Writes a checkpoint file after each spec passes within a task run.
On re-run, completed specs are skipped and their outputs are injected
into the propagator as if they had just finished — no re-generation.

Checkpoint lifecycle
────────────────────
Created  : first spec in a task passes
Updated  : each subsequent spec passes
Cleared  : task completes fully (all specs pass), or manually via CLI
Retained : task is partial or fails — next run resumes from last checkpoint

Invalidation
────────────
A checkpoint is invalidated (ignored and overwritten) if the task file
has changed since the checkpoint was written. Change is detected via a
SHA-256 hash of the task file's content. This prevents resuming from a
checkpoint that no longer matches the task definition.

File location
─────────────
.harness/checkpoints/{task-id}.json
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .task_models import SpecRun, TaskSpec
    from .models import GeneratedArtifact, GateResult, GateError, HarnessRun

log = logging.getLogger("harness.checkpoint")


# ── Stored types ──────────────────────────────────────────────────────────────

@dataclass
class CheckpointedSpec:
    """All data needed to reconstruct a completed SpecRun without re-running."""
    spec_id: str
    completed_at: str                # ISO datetime
    target_file: str | None
    implementation: str
    tests: str
    reasoning: str
    assumptions: list[str]
    notes: list[str]
    gate_results: list[dict]         # serialised GateResult list


@dataclass
class Checkpoint:
    task_id: str
    task_file_hash: str              # SHA-256 of task file — invalidates on change
    created_at: str
    updated_at: str
    completed_specs: dict[str, CheckpointedSpec] = field(default_factory=dict)

    def is_valid_for(self, task_file_path: str) -> bool:
        """Returns False if the task file has changed since this checkpoint was written."""
        try:
            current_hash = _hash_file(task_file_path)
            return current_hash == self.task_file_hash
        except OSError:
            return False

    def has(self, spec_id: str) -> bool:
        return spec_id in self.completed_specs

    def get(self, spec_id: str) -> CheckpointedSpec | None:
        return self.completed_specs.get(spec_id)


# ── Store ─────────────────────────────────────────────────────────────────────

class CheckpointStore:
    """
    Reads and writes checkpoint files for task runs.
    One checkpoint file per task, stored in .harness/checkpoints/.
    """

    def __init__(self, checkpoints_dir: str = ".harness/checkpoints"):
        self._dir = Path(checkpoints_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def load(self, task_id: str, task_file_path: str) -> Checkpoint | None:
        """
        Load checkpoint for task_id. Returns None if no checkpoint exists
        or if the checkpoint is invalid (task file has changed).
        """
        path = self._path(task_id)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            checkpoint = self._deserialise(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("Checkpoint for %s is corrupt (%s) — ignoring", task_id, e)
            return None

        if not checkpoint.is_valid_for(task_file_path):
            log.info(
                "Checkpoint for %s is stale (task file changed) — starting fresh",
                task_id,
            )
            path.unlink(missing_ok=True)
            return None

        completed = list(checkpoint.completed_specs.keys())
        log.info(
            "Resuming task %s — %d spec(s) already completed: %s",
            task_id, len(completed), completed,
        )
        return checkpoint

    def record_spec(
        self,
        task_id: str,
        task_file_path: str,
        spec_run: "SpecRun",
    ) -> None:
        """Record a completed spec into the checkpoint. Creates checkpoint if needed."""
        path = self._path(task_id)
        now = datetime.now(UTC).isoformat()

        # Load or create
        if path.exists():
            try:
                data = json.loads(path.read_text())
                checkpoint = self._deserialise(data)
            except Exception:
                checkpoint = self._new(task_id, task_file_path, now)
        else:
            checkpoint = self._new(task_id, task_file_path, now)

        checkpoint.updated_at = now
        artifact = spec_run.run.attempts[-1].artifact

        checkpoint.completed_specs[spec_run.task_spec.spec.id] = CheckpointedSpec(
            spec_id=spec_run.task_spec.spec.id,
            completed_at=now,
            target_file=spec_run.task_spec.spec.metadata.get("target_file"),
            implementation=artifact.implementation,
            tests=artifact.tests,
            reasoning=artifact.reasoning,
            assumptions=artifact.assumptions,
            notes=artifact.notes,
            gate_results=[
                {
                    "gate": g.gate,
                    "passed": g.passed,
                    "duration_ms": g.duration_ms,
                    "errors": [
                        {"message": e.message, "file": e.file,
                         "line": e.line, "code": e.code, "severity": e.severity}
                        for e in g.errors
                    ],
                }
                for g in spec_run.run.gate_results
            ],
        )

        path.write_text(json.dumps(self._serialise(checkpoint), indent=2))
        log.debug("Checkpoint updated: %s (%d spec(s))",
                  task_id, len(checkpoint.completed_specs))

    def clear(self, task_id: str) -> bool:
        """Delete checkpoint. Returns True if a checkpoint existed."""
        path = self._path(task_id)
        if path.exists():
            path.unlink()
            log.info("Checkpoint cleared: %s", task_id)
            return True
        return False

    def status(self, task_id: str) -> dict | None:
        """Return summary info about a checkpoint without full deserialisation."""
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return {
                "task_id": task_id,
                "updated_at": data.get("updated_at"),
                "completed_specs": list(data.get("completed_specs", {}).keys()),
            }
        except Exception:
            return None

    # ── Private ───────────────────────────────────────────────────────────────

    def _path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.json"

    def _new(self, task_id: str, task_file_path: str, now: str) -> Checkpoint:
        return Checkpoint(
            task_id=task_id,
            task_file_hash=_hash_file(task_file_path),
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _serialise(c: Checkpoint) -> dict:
        return {
            "task_id": c.task_id,
            "task_file_hash": c.task_file_hash,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "completed_specs": {
                sid: {
                    "spec_id": cs.spec_id,
                    "completed_at": cs.completed_at,
                    "target_file": cs.target_file,
                    "implementation": cs.implementation,
                    "tests": cs.tests,
                    "reasoning": cs.reasoning,
                    "assumptions": cs.assumptions,
                    "notes": cs.notes,
                    "gate_results": cs.gate_results,
                }
                for sid, cs in c.completed_specs.items()
            },
        }

    @staticmethod
    def _deserialise(data: dict) -> Checkpoint:
        specs = {}
        for sid, sd in data.get("completed_specs", {}).items():
            specs[sid] = CheckpointedSpec(
                spec_id=sd["spec_id"],
                completed_at=sd["completed_at"],
                target_file=sd.get("target_file"),
                implementation=sd["implementation"],
                tests=sd["tests"],
                reasoning=sd.get("reasoning", ""),
                assumptions=sd.get("assumptions", []),
                notes=sd.get("notes", []),
                gate_results=sd.get("gate_results", []),
            )
        return Checkpoint(
            task_id=data["task_id"],
            task_file_hash=data["task_file_hash"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            completed_specs=specs,
        )


# ── Reconstruction ────────────────────────────────────────────────────────────

def reconstruct_spec_run(
    task_spec: "TaskSpec",
    checkpointed: CheckpointedSpec,
) -> "SpecRun":
    """
    Rebuild a SpecRun from checkpoint data.
    The result is structurally identical to a live run's SpecRun —
    the propagator cannot distinguish it from one that just executed.
    """
    from .models import GeneratedArtifact, GateResult, GateError, HarnessRun
    from .task_models import SpecRun, Attempt

    artifact = GeneratedArtifact(
        implementation=checkpointed.implementation,
        tests=checkpointed.tests,
        reasoning=checkpointed.reasoning,
        assumptions=checkpointed.assumptions,
        notes=checkpointed.notes,
    )

    gate_results = [
        GateResult(
            gate=g["gate"],
            passed=g["passed"],
            duration_ms=g["duration_ms"],
            errors=[
                GateError(
                    message=e["message"],
                    file=e.get("file"),
                    line=e.get("line"),
                    column=None,
                    code=e.get("code"),
                    severity=e.get("severity", "error"),
                )
                for e in g.get("errors", [])
            ],
        )
        for g in checkpointed.gate_results
    ]

    run = HarnessRun(
        id="checkpointed",
        spec=task_spec.spec,
        attempts=[Attempt(
            number=1,
            artifact=artifact,
            gate_results=gate_results,
            repair_context=None,
        )],
        outcome="passed",
        total_duration_ms=0,
    )

    return SpecRun(task_spec=task_spec, run=run, blocked_by=None)


# ── Utility ───────────────────────────────────────────────────────────────────

def _hash_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@property
def gate_results(self: "HarnessRun") -> list:
    """Convenience: gate results from the last attempt."""
    return self.attempts[-1].gate_results if self.attempts else []

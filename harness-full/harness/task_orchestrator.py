"""
Task orchestrator: executes a multi-spec Task as a dependency-ordered DAG.

Execution model
───────────────
  - Specs in the same DAG layer run concurrently (ThreadPoolExecutor)
  - A failed spec marks all downstream dependents as BLOCKED
  - Completed specs propagate their public API into dependent specs before generation
  - Every run is recorded in the failure memory

Checkpointing
─────────────
  - After each spec passes, its output is written to a checkpoint file
  - On re-run of a partial/failed task, completed specs are skipped and
    their outputs reconstructed from the checkpoint
  - The checkpoint is cleared automatically when the full task passes
  - The checkpoint is invalidated (ignored) if the task file changes
"""

from __future__ import annotations
import concurrent.futures
import logging
import time
import uuid
from .dag import DAGResolver
from .propagator import ContextPropagator
from .checkpoint import CheckpointStore, reconstruct_spec_run
from .task_models import Task, TaskRun, SpecRun, TaskSpec
from .models import HarnessRun
from .orchestrator import InstrumentedOrchestrator

log = logging.getLogger("harness.task")


class TaskOrchestrator:
    def __init__(
        self,
        spec_orchestrator: InstrumentedOrchestrator,
        max_workers: int = 4,
        checkpoint_dir: str = ".harness/checkpoints",
    ):
        self._harness = spec_orchestrator
        self._resolver = DAGResolver()
        self._propagator = ContextPropagator()
        self._max_workers = max_workers
        self._checkpoints = CheckpointStore(checkpoint_dir)

    def run(self, task: Task, task_file_path: str = "") -> TaskRun:
        self._resolver.validate(task)
        layers = self._resolver.execution_layers(task)

        # ── Load checkpoint ───────────────────────────────────────────────────
        checkpoint = None
        if task_file_path:
            checkpoint = self._checkpoints.load(task.id, task_file_path)

        task_run = TaskRun(
            id=str(uuid.uuid4())[:8],
            task=task,
            spec_runs=[],
            outcome="failed",
        )
        t0 = time.monotonic()
        completed: dict[str, SpecRun] = {}
        failed_ids: set[str] = set()

        total_specs = len(task.specs)
        resumed = len(checkpoint.completed_specs) if checkpoint else 0

        log.info(
            "Task %s — %d spec(s) across %d layer(s)%s",
            task.id, total_specs, len(layers),
            f" (resuming: {resumed} already complete)" if resumed else "",
        )

        for layer_num, layer in enumerate(layers, 1):

            # ── Handle checkpointed specs in this layer ───────────────────────
            checkpointed_in_layer: list[TaskSpec] = []
            live_in_layer: list[TaskSpec] = []

            for ts in layer:
                if checkpoint and checkpoint.has(ts.spec.id):
                    checkpointed_in_layer.append(ts)
                else:
                    live_in_layer.append(ts)

            # Reconstruct checkpointed specs and add to completed map
            for ts in checkpointed_in_layer:
                stored = checkpoint.get(ts.spec.id)
                sr = reconstruct_spec_run(ts, stored)
                task_run.spec_runs.append(sr)
                completed[ts.spec.id] = sr
                log.info(
                    "  Layer %d/%d  ↩ RESTORED  %s  (from checkpoint)",
                    layer_num, len(layers), ts.spec.id,
                )

            # ── Determine runnable vs blocked among live specs ────────────────
            runnable = [ts for ts in live_in_layer
                        if not any(d in failed_ids for d in ts.depends_on)]
            blocked  = [ts for ts in live_in_layer
                        if any(d in failed_ids for d in ts.depends_on)]

            if live_in_layer:
                log.info(
                    "  Layer %d/%d — %d runnable, %d blocked, %d restored",
                    layer_num, len(layers),
                    len(runnable), len(blocked), len(checkpointed_in_layer),
                )

            for ts in blocked:
                blocker = next(d for d in ts.depends_on if d in failed_ids)
                sr = SpecRun(task_spec=ts, run=_stub_run(ts), blocked_by=blocker)
                task_run.spec_runs.append(sr)
                log.warning("    BLOCKED  %s  (upstream: %s)", ts.spec.id, blocker)

            if not runnable:
                continue

            # ── Enrich each runnable spec with upstream context ───────────────
            enriched_layer: list[TaskSpec] = []
            for ts in runnable:
                upstream = [completed[dep] for dep in ts.depends_on if dep in completed]
                enriched_spec = self._propagator.enrich(ts.spec, upstream)
                if upstream:
                    log.info(
                        "    Injected context from: %s → %s",
                        [sr.task_spec.spec.id for sr in upstream], ts.spec.id,
                    )
                enriched_layer.append(
                    TaskSpec(spec=enriched_spec, depends_on=ts.depends_on)
                )

            layer_results = self._run_layer(enriched_layer)

            for original_ts, sr in zip(runnable, layer_results):
                canonical = SpecRun(
                    task_spec=original_ts,
                    run=sr.run,
                    blocked_by=None,
                )
                task_run.spec_runs.append(canonical)
                completed[original_ts.spec.id] = canonical

                if canonical.run.outcome == "passed":
                    log.info("    PASSED   %s", original_ts.spec.id)
                    # Write checkpoint immediately after each pass
                    if task_file_path:
                        self._checkpoints.record_spec(
                            task.id, task_file_path, canonical
                        )
                else:
                    failed_ids.add(original_ts.spec.id)
                    log.warning("    FAILED   %s", original_ts.spec.id)

        task_run.total_duration_ms = int((time.monotonic() - t0) * 1000)
        task_run.outcome = _task_outcome(task_run)

        # ── Clear checkpoint on full pass ─────────────────────────────────────
        if task_run.outcome == "passed" and task_file_path:
            self._checkpoints.clear(task.id)

        log.info(
            "Task %s %s — %d/%d passed in %dms",
            task.id, task_run.outcome.upper(),
            len(task_run.passed_specs), len(task.specs),
            task_run.total_duration_ms,
        )
        return task_run

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_layer(self, layer: list[TaskSpec]) -> list[SpecRun]:
        if len(layer) == 1:
            run = self._harness.run(layer[0].spec)
            return [SpecRun(task_spec=layer[0], run=run)]

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(layer))
        ) as pool:
            futures = {
                pool.submit(self._harness.run, ts.spec): ts
                for ts in layer
            }
            results: list[SpecRun] = []
            for future in concurrent.futures.as_completed(futures):
                ts = futures[future]
                results.append(SpecRun(task_spec=ts, run=future.result()))

        order = {ts.spec.id: i for i, ts in enumerate(layer)}
        results.sort(key=lambda r: order[r.task_spec.spec.id])
        return results


def _task_outcome(task_run: TaskRun) -> str:
    if not task_run.failed_specs and not task_run.blocked_specs:
        return "passed"
    if task_run.passed_specs:
        return "partial"
    return "failed"


def _stub_run(ts: TaskSpec) -> HarnessRun:
    return HarnessRun(id="blocked", spec=ts.spec, attempts=[], outcome="escalated")

"""LLM Coding Harness — public API."""

from .models import Spec, GeneratedArtifact, HarnessRun, GateResult, GateError
from .config import HarnessConfig, LLMConfig, IndexConfig
from .factory import build_harness
from .orchestrator import InstrumentedOrchestrator
from .task_models import Task, TaskSpec, TaskRun, SpecRun
from .task_orchestrator import TaskOrchestrator
from .scorer import SpecScorer, SpecScore, DimensionScore
from .checkpoint import CheckpointStore, Checkpoint, CheckpointedSpec
from .index import PersistedVectorStore, IncrementalIndexer, SyncStats
from .sandbox import SandboxConfig, SandboxedGate, SandboxImageBuilder
from .memory import SQLiteFailureMemory, FailureRecord, BM25Index
from .escalator import RepairInstructionEscalator, FailurePattern

__all__ = [
    # Single-spec
    "Spec", "GeneratedArtifact", "HarnessRun", "GateResult", "GateError",
    "HarnessConfig", "LLMConfig", "IndexConfig",
    "build_harness", "InstrumentedOrchestrator",
    # Multi-spec
    "Task", "TaskSpec", "TaskRun", "SpecRun", "TaskOrchestrator",
    # Quality scoring
    "SpecScorer", "SpecScore", "DimensionScore",
    # Checkpointing
    "CheckpointStore", "Checkpoint", "CheckpointedSpec",
    # Incremental indexing
    "PersistedVectorStore", "IncrementalIndexer", "SyncStats",
    # Sandboxing
    "SandboxConfig", "SandboxedGate", "SandboxImageBuilder",
    # Memory + hybrid retrieval
    "SQLiteFailureMemory", "FailureRecord", "BM25Index",
    # Repair escalation
    "RepairInstructionEscalator", "FailurePattern",
]

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
from .verifier import (
    AdversarialVerifier, VerifierReport, VerifierFinding, ConstraintCheck,
)
from .hardener import (
    SpecHardener, HardeningReport, PinnedIdentifier, OpenAmbiguity,
)
from .novelty import (
    NoveltyClassifier, NoveltyAssessment, VerificationProfile,
)
from .alignment import AlignmentGate, AlignmentReport
from .consistency import (
    IdentifierConsistencyCheck, ConsistencyReport, ConsistencyViolation,
)

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
    # Adversarial verifier (Refinement 1)
    "AdversarialVerifier", "VerifierReport", "VerifierFinding", "ConstraintCheck",
    # Spec hardener (Refinement 2)
    "SpecHardener", "HardeningReport", "PinnedIdentifier", "OpenAmbiguity",
    # Novelty classifier (Refinement 4)
    "NoveltyClassifier", "NoveltyAssessment", "VerificationProfile",
    # Alignment gate (Refinement 5)
    "AlignmentGate", "AlignmentReport",
    # Identifier consistency check (Refinement 6)
    "IdentifierConsistencyCheck", "ConsistencyReport", "ConsistencyViolation",
]

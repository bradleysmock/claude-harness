"""
Protocol interfaces for all harness components.
The orchestrator depends only on these — never on concrete implementations.
Swap any component by implementing its Protocol.
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable
from .models import (
    Spec, GeneratedArtifact, GateResult, GateError,
    HarnessRun, MemoryStats,
)


@runtime_checkable
class ContextProvider(Protocol):
    """Retrieves relevant codebase context for a given spec."""
    def fetch(self, spec: Spec) -> list[str]: ...


@runtime_checkable
class LLMClient(Protocol):
    """Sends a prompt, returns a structured artifact."""
    def generate(self, spec: Spec) -> GeneratedArtifact: ...
    def repair(self, artifact: GeneratedArtifact,
               context: "RepairContext") -> GeneratedArtifact: ...


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Runs one gate against generated code. Implement per stack."""
    @property
    def gate_name(self) -> str: ...
    def run(self, artifact: GeneratedArtifact) -> GateResult: ...


@runtime_checkable
class Embedder(Protocol):
    """Converts text to a vector. Any embedding model satisfies this."""
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStore(Protocol):
    """Stores and retrieves indexed chunks by cosine similarity."""
    def upsert(self, chunks: list["IndexedChunk"]) -> None: ...
    def search(self, query_embedding: list[float],
               limit: int = 5) -> list["CodeChunk"]: ...
    def clear(self) -> None: ...


@runtime_checkable
class FailureMemory(Protocol):
    """Stores every run; retrieves similar past failures for repair context."""
    def record(self, run: HarnessRun) -> None: ...
    def retrieve_similar(self, errors: list[GateError],
                         gate: str, limit: int = 3) -> list[str]: ...
    def stats(self) -> MemoryStats: ...


@runtime_checkable
class EscalationHandler(Protocol):
    """Called when all retries are exhausted without passing."""
    def escalate(self, run: HarnessRun) -> None: ...

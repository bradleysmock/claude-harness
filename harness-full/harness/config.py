"""Harness configuration. One dataclass, all settings."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class LLMConfig:
    api_key: str
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0
    max_tokens: int = 8096
    prompt_retries: int = 2          # retries on JSON parse failure only


@dataclass
class IndexConfig:
    project_root: str
    convention_files: list[str] = field(default_factory=list)
    ignore_patterns: list[str] = field(default_factory=lambda: [
        ".git", "__pycache__", "node_modules", ".venv",
        "dist", "build", ".mypy_cache",
    ])
    max_chunks_per_query: int = 6
    max_chars_per_chunk: int = 1500
    index_db_path: str = ".harness/index.db"  # persisted vector store
    force_reindex: bool = False               # re-embed everything on next sync


@dataclass
class HarnessConfig:
    llm: LLMConfig
    index: IndexConfig
    db_path: str = ".harness/memory.db"
    max_retries: int = 3
    gate_timeout_seconds: int = 60
    log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"
    language: str = "python"          # python | typescript | go | rust
    sandbox: "SandboxConfig | None" = None  # None = unsandboxed (native)


# Import here to avoid circular; users can also import directly from harness.sandbox
def __getattr__(name):
    if name == "SandboxConfig":
        from .sandbox import SandboxConfig
        return SandboxConfig
    raise AttributeError(name)

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
class ConsistencyConfig:
    """Identifier consistency check configuration."""
    enabled: bool = True
    # AST-based check that pinned identifiers from the hardener actually
    # appear in the generated implementation. Catches reference drift
    # that compiles cleanly but violates explicit naming constraints.


@dataclass
class AlignmentConfig:
    """Spec-implementation alignment gate configuration."""
    enabled: bool = True
    threshold: float = 0.75
    # Verdict required for acceptance:
    #   - >= 0.85 always passes (verdict: aligned)
    #   - threshold <= score < 0.85 passes only if verdict != misaligned
    #   - < threshold always fails


@dataclass
class NoveltyConfig:
    """Novelty-calibrated verification configuration."""
    enabled: bool = True
    # When True, novelty classification can extend the retry budget and
    # trigger the human review flag on novel tasks. When False, all tasks
    # use the baseline configuration.


@dataclass
class HardenerConfig:
    """Spec hardening configuration."""
    enabled: bool = True
    block_on_open_ambiguities: bool = False
    # If True, the harness halts when the hardener finds unresolvable
    # ambiguities and requires human review. If False, generation proceeds
    # and the ambiguities are logged for post-hoc review.


@dataclass
class VerifierConfig:
    """Adversarial verifier configuration."""
    enabled: bool = True
    strict: bool = True              # reject if any criterion unverifiable
    # When False, verifier only runs on first attempt (cheaper, less rigorous).
    # When True, verifier runs every attempt that passes gates.
    run_every_attempt: bool = True


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
    verifier: VerifierConfig = field(default_factory=VerifierConfig)
    hardener: HardenerConfig = field(default_factory=HardenerConfig)
    novelty: NoveltyConfig = field(default_factory=NoveltyConfig)
    alignment: AlignmentConfig = field(default_factory=AlignmentConfig)
    consistency: ConsistencyConfig = field(default_factory=ConsistencyConfig)


# Import here to avoid circular; users can also import directly from harness.sandbox
def __getattr__(name):
    if name == "SandboxConfig":
        from .sandbox import SandboxConfig
        return SandboxConfig
    raise AttributeError(name)

"""
factory.py — Composition root. Wires all components from config.

Improvement #3: Uses IncrementalIndexer + PersistedVectorStore instead of
CodebaseIndexer + InMemoryVectorStore. First run indexes everything and
persists to .harness/index.db. Subsequent runs only re-embed changed files.

Improvement #5: Passes sandbox config through to orchestrator when set.
"""

from __future__ import annotations
from .config import HarnessConfig
from .context import (
    AnthropicEmbedder, SemanticChunker, CodebaseContextProvider,
)
from .index import PersistedVectorStore, IncrementalIndexer
from .llm.client import AnthropicLLMClient
from .memory import SQLiteFailureMemory
from .orchestrator import (
    EventBus, LoggingListener, LoggingEscalationHandler,
    InstrumentedOrchestrator,
)


def build_harness(config: HarnessConfig) -> InstrumentedOrchestrator:
    """Assemble and return a fully wired orchestrator."""

    bus = EventBus()
    bus.subscribe(LoggingListener(config.log_level))

    embedder = AnthropicEmbedder(api_key=config.llm.api_key)

    # ── Incremental index (persisted between runs) ─────────────────────────────
    store   = PersistedVectorStore(db_path=config.index.index_db_path)
    chunker = SemanticChunker()
    indexer = IncrementalIndexer(
        chunker, embedder, store,
        ignore_patterns=config.index.ignore_patterns,
    )

    stats = indexer.sync(
        config.index.project_root,
        force=config.index.force_reindex,
    )
    print(f"Index: {stats.summary()}")

    if config.index.convention_files:
        n = indexer.sync_conventions(config.index.convention_files)
        if n:
            print(f"Conventions: {n} file(s) updated")
        else:
            print("Conventions: up to date")

    context_provider = CodebaseContextProvider(
        embedder=embedder, store=store,
        max_chunks=config.index.max_chunks_per_query,
        max_chars_per_chunk=config.index.max_chars_per_chunk,
    )

    llm = AnthropicLLMClient(
        api_key=config.llm.api_key,
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_retries=config.llm.prompt_retries,
    )

    memory = SQLiteFailureMemory(db_path=config.db_path, embedder=embedder)

    if config.sandbox and config.sandbox.enabled:
        print(
            f"Sandbox: enabled ({config.sandbox.resolved_image()}, "
            f"network={config.sandbox.network})"
        )

    # ── Adversarial verifier (Refinement 1) ───────────────────────────────────
    verifier = None
    if config.verifier.enabled:
        from .verifier import AdversarialVerifier
        verifier = AdversarialVerifier(llm_client=llm, strict=config.verifier.strict)
        print(f"Verifier: enabled (strict={config.verifier.strict})")

    # ── Spec hardener (Refinement 2) ──────────────────────────────────────────
    hardener = None
    if config.hardener.enabled:
        from .hardener import SpecHardener
        hardener = SpecHardener(llm_client=llm)
        print(f"Hardener: enabled (block_on_open_ambiguities={config.hardener.block_on_open_ambiguities})")

    # ── Novelty classifier (Refinement 4) ─────────────────────────────────────
    classifier = None
    if config.novelty.enabled:
        from .novelty import NoveltyClassifier
        classifier = NoveltyClassifier(base_retries=config.max_retries)
        print("Novelty classifier: enabled")

    # ── Alignment gate (Refinement 5) ─────────────────────────────────────────
    alignment_gate = None
    if config.alignment.enabled:
        from .alignment import AlignmentGate
        alignment_gate = AlignmentGate(
            llm_client=llm, threshold=config.alignment.threshold,
        )
        print(f"Alignment gate: enabled (threshold={config.alignment.threshold})")

    # ── Identifier consistency check (Refinement 6) ───────────────────────────
    consistency_check = None
    if config.consistency.enabled:
        from .consistency import IdentifierConsistencyCheck
        consistency_check = IdentifierConsistencyCheck(language=config.language)
        print(f"Consistency check: enabled ({config.language})")

    return InstrumentedOrchestrator(
        context_provider=context_provider,
        llm=llm,
        memory=memory,
        escalation=LoggingEscalationHandler(),
        project_root=config.index.project_root,
        language=config.language,
        sandbox=config.sandbox,
        verifier=verifier,
        hardener=hardener,
        novelty_classifier=classifier,
        alignment_gate=alignment_gate,
        consistency_check=consistency_check,
        block_on_open_ambiguities=config.hardener.block_on_open_ambiguities,
        max_retries=config.max_retries,
        bus=bus,
    )

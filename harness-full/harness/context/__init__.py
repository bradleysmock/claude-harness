"""
Context provider: chunker, embedder, vector store, indexer, provider.
Retrieves semantically relevant codebase snippets to inject into LLM prompts.
"""

from __future__ import annotations
import ast
import hashlib
import math
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

import anthropic


# ── Types ─────────────────────────────────────────────────────────────────────

class ChunkKind(str, Enum):
    FUNCTION   = "function"
    CLASS      = "class"
    INTERFACE  = "interface"
    MODULE     = "module"
    CONVENTION = "convention"
    SCHEMA     = "schema"


@dataclass
class CodeChunk:
    id: str
    kind: ChunkKind
    content: str
    file_path: str
    symbol_name: str | None
    language: str | None
    metadata: dict = field(default_factory=dict)


@dataclass
class IndexedChunk:
    chunk: CodeChunk
    embedding: list[float]


# ── Embedder ──────────────────────────────────────────────────────────────────

class AnthropicEmbedder:
    """Uses Anthropic's embedding model. Satisfies the Embedder protocol."""
    MODEL = "voyage-code-3"

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Voyage API via Anthropic client
        response = self._client.embeddings.create(
            model=self.MODEL,
            input=texts,
        )
        return [r.embedding for r in response.data]


# ── Vector store ──────────────────────────────────────────────────────────────

class InMemoryVectorStore:
    """Reference implementation. Swap for Chroma/pgvector in production."""

    def __init__(self):
        self._store: list[IndexedChunk] = []

    def upsert(self, chunks: list[IndexedChunk]) -> None:
        existing = {ic.chunk.id for ic in self._store}
        self._store.extend(ic for ic in chunks if ic.chunk.id not in existing)

    def search(self, query_embedding: list[float], limit: int = 5) -> list[CodeChunk]:
        if not self._store:
            return []
        scored = [
            (self._cosine(query_embedding, ic.embedding), ic.chunk)
            for ic in self._store
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]

    def clear(self) -> None:
        self._store.clear()

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x ** 2 for x in a))
        mag_b = math.sqrt(sum(x ** 2 for x in b))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


# ── Chunker ───────────────────────────────────────────────────────────────────

class SemanticChunker:
    """
    Chunks source files at symbol boundaries.
    Uses tree-sitter when available; falls back to regex heuristics.
    """

    _CAPTURE_NODES = {
        "python":     {"function_definition", "class_definition"},
        "typescript": {"function_declaration", "class_declaration",
                       "interface_declaration", "type_alias_declaration",
                       "method_definition"},
        "go":         {"function_declaration", "method_declaration", "type_declaration"},
        "rust":       {"function_item", "impl_item", "struct_item", "trait_item"},
        "java":       {"method_declaration", "class_declaration", "interface_declaration"},
    }

    _FALLBACK = re.compile(
        r"((?:^|\n)(?:(?:async\s+)?(?:def|function|func|fn|class|interface|type"
        r"|export\s+(?:default\s+)?(?:function|class))\s+\w+[^\n]*\n"
        r"(?:(?!\n(?:def|function|func|fn|class|interface|type)\s).+\n?)*))",
        re.MULTILINE,
    )

    _EXTENSIONS = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "typescript", ".go": "go", ".rs": "rust", ".java": "java",
    }

    def chunk_file(self, path: str, content: str) -> list[CodeChunk]:
        lang = self._EXTENSIONS.get(Path(path).suffix)
        try:
            import tree_sitter_languages as tsl
            if lang and lang in self._CAPTURE_NODES:
                chunks = self._chunk_ts(path, content, lang, tsl)
            else:
                chunks = self._chunk_regex(path, content, lang)
        except ImportError:
            chunks = self._chunk_regex(path, content, lang)

        if not chunks and len(content) < 4000:
            chunks = [self._make(content, path, ChunkKind.MODULE, lang)]
        return chunks

    def _chunk_ts(self, path, content, lang, tsl):
        parser = tsl.get_parser(lang)
        tree = parser.parse(content.encode())
        target = self._CAPTURE_NODES[lang]
        chunks = []

        def walk(node):
            if node.type in target:
                text = content[node.start_byte:node.end_byte]
                name = next(
                    (content[c.start_byte:c.end_byte]
                     for c in node.children if c.type == "identifier"),
                    None,
                )
                kind = (ChunkKind.CLASS if "class" in node.type
                        else ChunkKind.INTERFACE if "interface" in node.type
                        else ChunkKind.FUNCTION)
                chunks.append(self._make(text, path, kind, lang, name))
                return
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return chunks

    def _chunk_regex(self, path, content, lang):
        return [
            self._make(m.group(0).strip(), path, ChunkKind.FUNCTION, lang)
            for m in self._FALLBACK.finditer(content)
            if len(m.group(0).strip()) > 50
        ]

    @staticmethod
    def _make(content, path, kind, lang, name=None):
        return CodeChunk(
            id=hashlib.sha256(content.encode()).hexdigest()[:16],
            kind=kind, content=content, file_path=path,
            symbol_name=name, language=lang,
        )


# ── Indexer ───────────────────────────────────────────────────────────────────

class CodebaseIndexer:
    _SOURCE_EXTS = {".py",".ts",".tsx",".js",".go",".rs",".java",".md",".yaml",".json"}

    def __init__(self, chunker: SemanticChunker, embedder, store,
                 ignore_patterns: list[str] | None = None):
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._ignore = set(ignore_patterns or [
            ".git","__pycache__","node_modules",".venv","dist","build",".mypy_cache",
        ])

    def index_directory(self, root: str) -> int:
        chunks: list[CodeChunk] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self._ignore]
            for fn in filenames:
                if Path(fn).suffix not in self._SOURCE_EXTS:
                    continue
                try:
                    content = Path(os.path.join(dirpath, fn)).read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    chunks.extend(self._chunker.chunk_file(
                        os.path.join(dirpath, fn), content
                    ))
                except OSError:
                    continue
        if not chunks:
            return 0
        texts = [f"File: {c.file_path}\nSymbol: {c.symbol_name}\n\n{c.content}"
                 for c in chunks]
        embeddings = self._embedder.embed_batch(texts)
        self._store.upsert([IndexedChunk(c, e) for c, e in zip(chunks, embeddings)])
        return len(chunks)

    def index_conventions(self, paths: list[str]) -> None:
        chunks = []
        for path in paths:
            try:
                content = Path(path).read_text(encoding="utf-8")
                chunks.append(CodeChunk(
                    id=hashlib.sha256(content.encode()).hexdigest()[:16],
                    kind=ChunkKind.CONVENTION, content=content,
                    file_path=path, symbol_name=None, language=None,
                ))
            except OSError:
                continue
        if chunks:
            embeddings = self._embedder.embed_batch([c.content for c in chunks])
            self._store.upsert([IndexedChunk(c, e) for c, e in zip(chunks, embeddings)])


# ── Context provider ──────────────────────────────────────────────────────────

class CodebaseContextProvider:
    """Satisfies the ContextProvider protocol."""

    _ALWAYS_INCLUDE = {ChunkKind.CONVENTION}

    def __init__(self, embedder, store,
                 max_chunks: int = 6, max_chars_per_chunk: int = 1500):
        self._embedder = embedder
        self._store = store
        self._max_chunks = max_chunks
        self._max_chars = max_chars_per_chunk

    def fetch(self, spec) -> list[str]:
        query = spec.description + "\n" + "\n".join(spec.constraints[:3])
        embedding = self._embedder.embed(query)
        chunks = self._store.search(embedding, limit=self._max_chunks + 4)
        conventions = [c for c in chunks if c.kind in self._ALWAYS_INCLUDE]
        code = [c for c in chunks if c.kind not in self._ALWAYS_INCLUDE]
        return [self._format(c) for c in conventions + code[:self._max_chunks]]

    def _format(self, chunk: CodeChunk) -> str:
        header = f"### {chunk.kind.value.upper()} — {chunk.file_path}"
        if chunk.symbol_name:
            header += f" ({chunk.symbol_name})"
        content = chunk.content
        if len(content) > self._max_chars:
            content = content[:self._max_chars] + "\n... [truncated]"
        return f"{header}\n\n```\n{content}\n```"

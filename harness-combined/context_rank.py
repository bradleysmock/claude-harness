"""Local context packages (ticket 0076).

`gather_context()` assembles a ranked snippet pack from local tools already
available (ripgrep, optionally ast-grep) — no indexing daemon, no new
service. Named `context_rank`, not `context_fetch`: `server.py` already
registers an unrelated MCP tool of that name.

`gather_context` and `describe_environment` are both pure — no logging, no
raising on a missing tool. Caching and disk I/O live in `get_or_generate_pack`,
the actual I/O boundary; callers (`commands/problem.md`, `build-ticket.md`)
log `describe_environment()`'s message themselves.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from memory import tokenize

#: Total lines across every snippet in one pack — keeps a pack from crowding
#: out the model's own context budget.
MAX_TOTAL_LINES = 200

#: Lines of surrounding context above/below a snippet's best-matching line.
_SNIPPET_WINDOW = 2

#: Query tokens shorter than this are too generic to search on usefully.
_MIN_TOKEN_LEN = 3

_EXEC_TIMEOUT = 15


@dataclass(frozen=True)
class Snippet:
    file: str
    lines: tuple[int, int]
    text: str
    score: float


def _exec(command: list[str], cwd: str | Path, timeout: int = _EXEC_TIMEOUT) -> subprocess.CompletedProcess:
    """Argv-list, `shell=False` exec helper modeled on `gates/go.py`'s `_exec`
    — not `gates/python.py`'s, which is bound to a `tempfile.mkdtemp()`
    sandbox, not a live project root."""
    return subprocess.run(
        command, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, shell=False,
    )


def _query_terms(query: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokenize(query):
        if len(token) < _MIN_TOKEN_LEN or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _rg_hits(term: str, project_root: str) -> list[tuple[str, int]]:
    """(file, line) hits for one fixed-string term. `[]` on any failure —
    absent binary, timeout, or no matches — never raises."""
    if shutil.which("rg") is None:
        return []
    try:
        result = _exec(["rg", "-Fn", "-i", "--no-heading", "--", term, "."], project_root)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode not in (0, 1):  # 1 = ran cleanly, no matches
        return []
    hits: list[tuple[str, int]] = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        file_path, line_no_text, _rest = parts
        if file_path.startswith("./"):
            file_path = file_path[2:]
        try:
            hits.append((file_path, int(line_no_text)))
        except ValueError:
            continue
    return hits


def gather_context(query: str, project_root: str, max_snippets: int = 5) -> list[Snippet]:
    """Rank `rg -Fn` hits by how many distinct query terms co-occur in each
    file. Pure: absent `rg` yields `[]`; no logging, no raising."""
    terms = _query_terms(query)
    if not terms:
        return []

    file_terms: dict[str, set[str]] = {}
    file_line_hits: dict[str, dict[int, set[str]]] = {}
    for term in terms:
        for file_path, line_no in _rg_hits(term, project_root):
            file_terms.setdefault(file_path, set()).add(term)
            file_line_hits.setdefault(file_path, {}).setdefault(line_no, set()).add(term)

    ranked_files = sorted(
        file_terms, key=lambda f: (-len(file_terms[f]), f),
    )[:max_snippets]

    root = Path(project_root)
    snippets: list[Snippet] = []
    total_lines = 0
    for file_path in ranked_files:
        remaining_budget = MAX_TOTAL_LINES - total_lines
        if remaining_budget <= 0:
            break
        line_hits = file_line_hits[file_path]
        best_line = max(line_hits, key=lambda ln: (len(line_hits[ln]), -ln))
        try:
            all_lines = (root / file_path).read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            continue
        start = max(1, best_line - _SNIPPET_WINDOW)
        end = min(len(all_lines), best_line + _SNIPPET_WINDOW)
        window = all_lines[start - 1:end]
        if len(window) > remaining_budget:
            window = window[:remaining_budget]
            end = start + len(window) - 1
        total_lines += len(window)
        snippets.append(Snippet(
            file=file_path, lines=(start, end),
            text="\n".join(window), score=float(len(file_terms[file_path])),
        ))
    return snippets


def describe_environment(project_root: str) -> str | None:
    """One-line degrade notice for the caller to log, or `None` if nothing to
    report. Pure — never logs itself."""
    missing = []
    if shutil.which("rg") is None:
        missing.append("rg not found — context pack will be empty")
    if shutil.which("ast-grep") is None:
        missing.append("ast-grep not found — degraded to keyword ranking only")
    if not missing:
        return None
    return "context_rank: " + "; ".join(missing)


def _git_output(command: list[str], project_root: str) -> str:
    try:
        result = _exec(command, project_root, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _cache_key(query: str, project_root: str) -> str:
    head = _git_output(["git", "rev-parse", "HEAD"], project_root)
    dirty = _git_output(["git", "status", "--porcelain"], project_root)
    raw = "\x00".join([query, head, dirty])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_CACHE_KEY_PREFIX = "<!-- context-rank-cache-key: "
_CACHE_KEY_SUFFIX = " -->"


def _render_pack(snippets: list[Snippet], cache_key: str) -> str:
    lines = [f"{_CACHE_KEY_PREFIX}{cache_key}{_CACHE_KEY_SUFFIX}", "# Context Pack", ""]
    if not snippets:
        lines.append("_No relevant snippets found._")
    for snippet in snippets:
        lines.append(f"## {snippet.file}:{snippet.lines[0]}-{snippet.lines[1]} (score {snippet.score:.1f})")
        lines.append("```")
        lines.append(snippet.text)
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _cached_key(pack_path: Path) -> str | None:
    if not pack_path.exists():
        return None
    try:
        first_line = pack_path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    if not (first_line.startswith(_CACHE_KEY_PREFIX) and first_line.endswith(_CACHE_KEY_SUFFIX)):
        return None
    return first_line[len(_CACHE_KEY_PREFIX):-len(_CACHE_KEY_SUFFIX)]


def get_or_generate_pack(
    query: str, project_root: str, ticket: str, max_snippets: int = 5
) -> str:
    """Return the cached pack for `(query, HEAD, dirty-tree state)` if it
    matches `.harness/context/<ticket>.md`'s stored key, else regenerate,
    write, and return the new pack. The only I/O boundary in this module."""
    cache_key = _cache_key(query, project_root)
    pack_path = Path(project_root) / ".harness" / "context" / f"{ticket}.md"
    if _cached_key(pack_path) == cache_key:
        return pack_path.read_text(encoding="utf-8")

    snippets = gather_context(query, project_root, max_snippets)
    content = _render_pack(snippets, cache_key)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(content, encoding="utf-8")
    return content

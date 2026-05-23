# harness-no-api-key — Design

## The one-line shift

**harness-full**: Python orchestrates a loop; Claude is a remote service it calls via API key.  
**harness-no-api-key**: Claude IS the orchestrator; Python provides tools for gates, files, and memory.

---

## What requires an API key in harness-full

| Component | What it does | How we replace it |
|---|---|---|
| `AnthropicLLMClient.generate()` | Produces implementation + tests | Claude generates inline during `/harness:submit` |
| `AnthropicLLMClient.repair()` | Fixes failed artifacts | Claude repairs inline after seeing gate errors |
| `AnthropicEmbedder.embed()` | Embeds code chunks for semantic search | Dropped — `context_fetch` reads `reference_files` directly |
| `AdversarialVerifier` | Separate LLM reviews the output | Dropped — Claude self-reviews before writing |
| `SpecHardener` | LLM pins identifiers, surfaces ambiguities | Folded into `/harness:forge` — Claude does this during spec writing |
| `NoveltyClassifier` | LLM classifies task difficulty | Dropped — Claude assesses naturally |
| `AlignmentGate` | LLM checks intent vs implementation | Dropped — Claude checks naturally |

**What stays as-is (pure Python, no API calls):**
- Gate execution: syntax, mypy, ruff, bandit, pytest — all subprocess
- Spec scoring — rule-based regex, no LLM
- BM25 failure memory — keyword search over SQLite
- DAG validation — topological sort
- Checkpointing — file I/O
- SemanticChunker — regex/tree-sitter, no API

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Claude Code (subscription auth)            │
│                                             │
│  Reads specs → generates implementation     │
│  Reads gate errors → repairs implementation │
│  Reads DAG → sequences spec execution       │
│  Reads results → delivers code              │
└──────────────────┬──────────────────────────┘
                   │ MCP tool calls
┌──────────────────▼──────────────────────────┐
│  harness-no-api-key MCP server              │
│                                             │
│  gate_run()        — subprocess gates       │
│  spec_load()       — read spec file         │
│  context_fetch()   — read reference files   │
│  artifact_save()   — write run to disk      │
│  artifact_load()   — read run from disk     │
│  memory_record()   — write failure to SQLite│
│  memory_retrieve() — BM25 search failures   │
│  dag_load()        — validate + layer DAG   │
│  checkpoint_read() — task resume            │
│  checkpoint_write()— task checkpoint        │
│  harness_status()  — recent runs            │
└─────────────────────────────────────────────┘
```

---

## MCP tools

### `gate_run(implementation, tests, language, project_root)`
Writes implementation and tests to a temp directory and runs the full gate suite for the given language. Returns structured results: each gate's pass/fail status, errors with file/line/code, and duration.

Gates per language (same as harness-full):
- Python: syntax → mypy → ruff → bandit → pytest
- TypeScript: tsc → eslint → jest
- Go: build → vet → staticcheck → test
- Rust: check → clippy → test

Returns on first gate failure (fail-fast). Missing tools are skipped gracefully.

### `spec_load(spec_id, project_root)`
Loads `.harness/specs/<spec_id>.py`, executes it in a restricted namespace, and returns the `Spec` as JSON: id, description, constraints, acceptance_criteria, metadata (target_file, reference_files).

### `context_fetch(reference_files, target_file, project_root)`
Reads the files listed in `reference_files` and the directory adjacent to `target_file`. Returns their content, truncated to fit context. No embeddings — well-specified reference_files give better, more predictable context than semantic search over a noisy codebase anyway.

### `artifact_save(spec_id, implementation, tests, outcome, attempts, gate_results, notes)`
Writes `.harness/results/<spec_id>-<timestamp>.json`. Outcome is `passed` or `escalated`. Stores the full attempt history so `/harness:finish` and `/harness:debug` have everything they need.

### `artifact_load(run_id, project_root)`
Reads a result file and returns it as JSON.

### `memory_record(spec_id, gate, errors, attempt_number, outcome)`
Writes the run to `.harness/memory.db` (SQLite). BM25-indexes the error text for later retrieval.

### `memory_retrieve(errors, gate, limit)`
BM25 keyword search over past failures matching the same gate. Returns formatted narrative of similar failures and how they were resolved. Used to guide repair.

### `dag_load(task_id, project_root)`
Loads `.harness/tasks/<task_id>.py`, validates the DAG (no cycles, all dependencies exist), and returns the execution layers in order — each layer is a list of spec IDs that can be worked on once the previous layer is complete.

### `checkpoint_read(task_id, project_root)` / `checkpoint_write(task_id, completed, project_root)`
Reads/writes `.harness/checkpoints/<task_id>.json`. Lets a task resume after partial completion without regenerating already-passed specs.

### `harness_status(project_root)`
Lists recent result files with spec ID, outcome, timestamp, and which gate failed (if escalated).

---

## Slash commands

All eight commands from harness-full-mcp are preserved. The only ones with meaningfully different internals are `submit` and `task`.

### `/harness:init`
Same as before — creates directories, writes config template, installs commands.

Config is simpler now:
```python
config = HarnessConfig(
    project_root="./src",
    language="python",       # python | typescript | go | rust
    max_repair_attempts=3,
)
```
No API key. No LLM config.

### `/harness:forge <description>`
Same as before — Claude explores, writes spec, self-reviews. No change.

### `/harness:forge-task <description>`
Same as before — Claude decomposes, writes task DAG. No change.

### `/harness:submit <spec-id>`

```
1. spec_load("$ARGUMENTS")
   → read spec: description, constraints, acceptance_criteria, reference_files, target_file

2. context_fetch(reference_files, target_file)
   → read relevant source files into context

3. Generate implementation and tests.
   Write them in clearly delimited blocks so the gate tool can extract them.

4. gate_run(implementation, tests, language)
   → structured pass/fail + errors per gate

5a. If all gates pass:
    - memory_record(..., outcome="passed")
    - artifact_save(..., outcome="passed")
    - Tell user: run /harness:finish

5b. If any gate fails (repeat up to max_repair_attempts):
    - memory_retrieve(errors, failed_gate)
    - Review gate errors + similar past failures
    - Repair implementation, keeping tests unchanged unless they are the bug
    - Go to step 4

5c. If still failing after max_repair_attempts:
    - memory_record(..., outcome="escalated")
    - artifact_save(..., outcome="escalated")
    - Tell user: run /harness:debug
```

The repair loop runs entirely within Claude's context window. Gate errors are concrete (line numbers, rule codes) and Claude has the full implementation, tests, spec, and similar past failures available simultaneously — this is actually a better repair context than harness-full had, where the repair LLM call was stateless.

### `/harness:task <task-name>`

```
1. dag_load("$ARGUMENTS")
   → validated layers: [[spec-a, spec-b], [spec-c], [spec-d]]

2. checkpoint_read("$ARGUMENTS")
   → skip already-passed specs

3. For each layer, for each spec in the layer:
   a. spec_load(spec_id)
   b. If spec has upstream dependencies: inject their saved implementations
      as additional context (so downstream knows exact APIs to call)
   c. Run the submit loop (steps 1–5 of /harness:submit above)
   d. If passed: checkpoint_write(...)
   e. If escalated: record it, skip dependent specs, continue with independent ones

4. Report: passed/escalated counts per layer, which specs to /harness:debug
```

Note: specs execute sequentially, not in parallel. Within a single Claude Code session there is no concurrency. For a 4-spec feature the wall-clock time is 4× the per-spec time. This is acceptable — the original parallelism was an optimization for API throughput, not a correctness requirement.

Upstream API injection replaces the `ContextPropagator` from harness-full. Instead of extracting a formal AST-based public interface, Claude reads the upstream implementation directly and infers what to import and call — which is more flexible anyway.

### `/harness:finish`
Same as before — reads result file, moves code to target_file, writes commit, opens draft PR.

### `/harness:debug`
Same as before — classifies failure (Class A–E), proposes spec edits.

### `/harness:status`
Calls `harness_status()`, shows recent runs.

---

## What is dropped vs harness-full

| harness-full feature | Status | Reason |
|---|---|---|
| `AnthropicEmbedder` + vector store | Dropped | No API key; `reference_files` + direct reads are more predictable |
| `AdversarialVerifier` | Dropped | Claude self-reviews during generation |
| `SpecHardener` | Folded into forge | Claude hardens spec during writing |
| `NoveltyClassifier` | Dropped | Claude assesses naturally |
| `AlignmentGate` | Dropped | Claude checks naturally |
| `IdentifierConsistencyCheck` | Dropped | Claude maintains consistency in-context |
| Parallel task execution | Dropped | Single-session sequential; correctness unaffected |
| Hybrid BM25+embedding memory | BM25 only | No embeddings; still useful for exact-error matching |
| Docker sandbox | Dropped | Gates run in-process; sandbox was optional in harness-full too |
| `python -m harness` CLI | Dropped | Claude Code is the entrypoint; no standalone CLI needed |

---

## Directory structure

```
harness-no-api-key/
├── DESIGN.md
├── .claude-plugin/
│   └── plugin.json                  name: "harness"
├── .mcp.json                        points to bin/harness-server
├── bin/
│   └── harness-server               self-bootstrapping venv wrapper
├── commands/
│   ├── init.md
│   ├── forge.md
│   ├── forge-task.md
│   ├── submit.md                    ← primary change vs harness-full-mcp
│   ├── task.md                      ← primary change vs harness-full-mcp
│   ├── finish.md
│   ├── debug.md
│   └── status.md
├── server.py                        MCP server — gates, files, memory, DAG
├── gates/
│   ├── __init__.py                  gate_suite_for(language) registry
│   ├── python.py                    ported from harness-full (unchanged)
│   ├── typescript.py
│   ├── go.py
│   └── rust.py
├── memory.py                        SQLite + BM25, no embedder dependency
├── dag.py                           DAG validation + layering (from harness-full)
├── models.py                        Spec, GateResult, HarnessRun (simplified)
└── requirements.txt                 mcp>=1.0 only
```

---

## Dependencies

```
mcp>=1.0
```

System tools (subprocess, not pip):
- Python gates: ruff, mypy, bandit, pytest
- TypeScript gates: tsc, eslint, jest (via npx)
- Go gates: go, staticcheck
- Rust gates: cargo

No anthropic SDK. No pydantic (gate results are plain dicts). No SQLite driver (stdlib). No tree-sitter (optional, falls back to regex).

---

## Open questions before implementation

1. **Output format for generation**: Claude needs to write implementation and tests in a structured format that `gate_run` can extract. Fenced code blocks with language tags are the natural choice — confirm this is robust enough before coding the extraction logic.

2. **Context window pressure for tasks**: Running multiple specs sequentially in one session accumulates context. A 6-spec task will have 6 implementations + gate results in context by the end. This may require `/clear` between task invocations for large features. The design should include a note in `/harness:task` about this.

3. **BM25 memory value**: With no embeddings, memory retrieval is purely keyword-based. For gate errors that are idiomatic (e.g., `E501 line too long`) this is fine. For novel errors it may return nothing useful. This is acceptable — the memory is a hint, not a requirement.

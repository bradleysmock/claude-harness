# LLM Coding Harness

A collaborative workflow for AI-assisted feature development.

**Claude Code** handles exploration and understanding.
**The harness** handles generation, verification, and memory.
**You** govern intent and review outcomes.

---

## Architecture

```
Claude Code (divergent)          Harness (convergent)
────────────────────             ────────────────────
Understands the problem          Executes the solution
Explores the codebase            Generates + gates code
Writes specs and tasks           Repairs failures
Interprets results               Remembers what failed
```

### System components

```
harness/
├── models.py              Core types: Spec, GeneratedArtifact, HarnessRun
├── protocols.py           Abstract interfaces (swap any component)
├── config.py              HarnessConfig
├── factory.py             build_harness() — wires all components
├── orchestrator.py        Single-spec loop: generate → gate → repair
├── task_models.py         Task, TaskSpec, TaskRun, SpecRun
├── dag.py                 DAG validation + topological sort
├── propagator.py          Context propagation between dependent specs
├── task_orchestrator.py   Multi-spec loop: layer → concurrent → propagate
├── cli.py                 python -m harness <command>
├── llm/                   Anthropic client + prompt builder
├── context/               Semantic chunker, embedder, vector store, RAG
├── gates/                 Syntax, type_check, lint, test, security gates
├── memory/                SQLite failure memory
└── commands/              Claude Code slash commands (copied to .claude/ on init)
```

---

## Installation

```bash
pip install anthropic pydantic
pip install mypy ruff bandit pytest          # gate tools
pip install tree-sitter-languages            # optional: better chunking
```

---

## Setup

```bash
cd your-repo
python -m harness init
# Edit .harness/config.py — add your API key and source root
```

---

## Workflows

### Single-spec (isolated function, endpoint, migration)

```bash
# 1. Claude Code explores codebase, writes .harness/specs/{name}.py
make forge TASK="add get_user_by_email to the user service"

# 2. Optional: review spec before running
make review SPEC=user-service-get-by-email

# 3. Run harness: generate → gate → repair → result
make submit SPEC=user-service-get-by-email

# 4a. On pass: move file + open draft PR
make finish RUN=user-service-get-by-email

# 4b. On escalation: Claude Code classifies failure, proposes spec fix
make debug RUN=user-service-get-by-email
# → apply fixes to spec → make submit again
```

### Multi-spec task (full feature, multiple coordinated components)

```bash
# 1. Claude Code decomposes feature into a DAG, writes .harness/tasks/{name}.py
make forge-task FEATURE="add per-user rate limiting to the payments API"

# 2. Run the full task DAG
make task TASK=payments-rate-limiting
# → Layer 1: redis-rate-limiter + rate-limit-config run in parallel
# → Layer 2: middleware (receives injected API from layer 1)
# → Layer 3: registration (receives injected API from layer 2)

# 3a. On pass: move all files + open draft PR
make finish-task RUN=payments-rate-limiting

# 3b. On partial/failure: debug the failed spec
make debug-task RUN=payments-rate-limiting
```

---

## The Spec Format

```python
# .harness/specs/my-spec.py
from harness import Spec

spec = Spec(
    id="my-spec",
    description="One precise paragraph. What, not how.",
    constraints=[
        # Name specific classes, methods, patterns.
        # Vague constraints → vague code.
    ],
    acceptance_criteria=[
        # Testable assertions only.
        # "Returns X when Y" — not "handles Y correctly".
    ],
    metadata={
        "target_file": "src/services/my_service.py",
        "reference_files": ["src/services/existing_service.py"],
    },
)
```

## The Task Format

```python
# .harness/tasks/my-task.py
# Dependency graph:
#   spec-a ──┐
#            ├──► spec-c
#   spec-b ──┘

from harness import Spec
from harness.task_models import Task, TaskSpec

task = Task(
    id="my-task",
    description="What feature this delivers.",
    specs=[
        TaskSpec(spec=Spec(id="spec-a", ...), depends_on=[]),
        TaskSpec(spec=Spec(id="spec-b", ...), depends_on=[]),
        TaskSpec(spec=Spec(id="spec-c", ...), depends_on=["spec-a", "spec-b"]),
    ],
)
```

**Context propagation is automatic.** When `spec-a` passes, its public API
is extracted and injected into `spec-c`'s constraints and examples before
generation — no manual wiring needed.

---

## Claude Code Commands

Installed to `.claude/commands/` by `make init`. Invoke with `/command-name` in Claude Code.

| Command | When to use |
|---|---|
| `/forge-spec` | Explore codebase → write a single spec |
| `/forge-task` | Explore codebase → write a multi-spec task DAG |
| `/review-spec` | Validate a spec for completeness before submitting |
| `/finish-task` | Move generated files, write commit, open draft PR |
| `/debug-escalation` | Classify a failure, propose spec corrections |

---

## Gate Sequence (Python adapter)

Gates run cheapest → most expensive. A failure stops the sequence.

| Gate | Tool | Typical duration |
|---|---|---|
| syntax | `ast.parse()` | ~5ms |
| type_check | `mypy` | ~2s |
| lint | `ruff` | ~0.5s |
| test | `pytest` | ~5–30s |
| security | `bandit` | ~1s |

---

## Swapping Components

Every component satisfies a `Protocol` in `harness/protocols.py`.

```python
# Swap vector store
from harness.context import ChromaVectorStore   # your implementation
store = ChromaVectorStore(persist_directory="./chroma")

# Swap embedder
from harness.protocols import Embedder
class LocalEmbedder:
    def embed(self, text): ...
    def embed_batch(self, texts): ...

# Swap escalation
class SlackEscalationHandler:
    def escalate(self, run): ...  # post to #engineering-alerts
```

---

## Failure Memory

Every run is recorded. Similar past failures are retrieved and injected into
repair context. The system gets cheaper and faster as memory grows.

```bash
make stats
# Total runs:       247
# Resolution rate:  84.2%
# Mean attempts:    1.71
# Failures by gate:
#   type_check       89
#   test             61
#   lint             24
```

High `type_check` failures → specs need richer type information.
High `test` failures → acceptance criteria need to be more specific.
Recurring `lint` failures → add a convention to `CONVENTIONS.md`.

---

## CI Integration

CI runs the same harness locally — identical gates, identical results.

```yaml
# .github/workflows/harness.yml
on:
  push:
    paths: ['.harness/specs/**.py', '.harness/tasks/**.py']

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r harness/requirements.txt
      - name: Run changed specs/tasks
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          git diff --name-only HEAD~1 HEAD -- '.harness/specs/*.py' \
            | xargs -I{} python -m harness submit {}
          git diff --name-only HEAD~1 HEAD -- '.harness/tasks/*.py' \
            | xargs -I{} python -m harness task {}
```

A local pass is a meaningful guarantee — the harness is the machine.

---

## See Also

- `examples/tasks/payments-rate-limiting.py` — annotated multi-spec task
- `.harness/config.py` — your repo's harness configuration
- `.claude/commands/` — Claude Code slash commands

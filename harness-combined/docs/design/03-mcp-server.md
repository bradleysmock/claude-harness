# MCP Server Design

Part 4 of the design series. See [00-overview.md](00-overview.md) for how this fits into the whole system and [01-gates-and-hooks.md](01-gates-and-hooks.md) for the gate logic several of these tools wrap. This document covers `server.py` itself, every tool it exposes, the core data models, and the supporting Python modules that back the ticket lifecycle, memory, and diagnostics.

---

## Architecture

`server.py` is a single-file FastMCP server (`mcp.server.fastmcp.FastMCP("harness")`) exposing 13 tools via `@mcp.tool()` decorators, running over stdio (`mcp.run()`). It's the *only* piece of the plugin that needs the third-party `mcp` package — everything else (hooks, `ticket.py`, the flow-referenced helper scripts) is stdlib plus local modules.

**Bootstrap.** `bin/harness-server` resolves the plugin root from its own script location and checks for `.venv/bin/python`. If that's missing, or `mcp` fails to import under it, the script creates a plugin-local virtualenv with `python3` (overridable via `HARNESS_PYTHON`), installs `requirements.txt`, then `exec`s `server.py` under that interpreter. This keeps the harness working under an externally-managed system Python (PEP 668) without polluting global site-packages. The venv is git-ignored and self-healing — it rebuilds automatically if deleted or if `mcp` stops importing. First launch takes roughly 30 seconds while the venv builds; every subsequent launch is instant. All bootstrap diagnostics go to stderr, since stdout is the JSON-RPC channel.

**Why the hooks don't need this.** `pre_write_guard.py`, `post_write_gate.py`, and `stop_full_gate.py` run on bare `python3` — they import only the standard library and the plugin's own modules, never `mcp` — so write-time and turn-end enforcement works even before the MCP server's first bootstrap completes, and never pays the venv cost at all.

---

## MCP tool catalog

Thirteen tools, all in `server.py`. (Note: the plugin's own `README.md` documents only nine of these — `commit_lint`, `doctor`, and `gate_run_red_check` are real, registered tools, not just file references, even though the README's MCP table omits them.)

| Tool | Workflow | Purpose |
|---|---|---|
| `gate_run(implementation, tests, language, project_root)` | Spec/build | Text-mode gate suite on generated code (fail-fast). Returns `{"passed": true, "duration_ms": N}` or a failing `GateResult`; adds a `skipped_tools` key when any gate warns `TOOL_SKIPPED`. |
| `gate_run_on_dir(directory, language, project_root, fail_fast=True, changed_files=None, emit_sarif=False)` | Ticket/SDLC | Directory-mode suite, one call per detected stack when `language="auto"`. Loads `[gates]`/`[policy]`/`parallel_gate_limit`/`[external_gates]` from `_standards.md` (fail-closed `CONFIG_ERROR` on malformed config). More than 10,000 `changed_files` entries degrades to "run everything" rather than risk an incomplete scope. |
| `gate_run_red_check(directory, language, test_file, node_ids, attempt, max_attempts, timeout=60)` | Ticket/SDLC (TDD) | Runs only the new spec's test(s) via `gates.red_gate.check_red`; classifies `red`/`blocking`/`tool_error` and returns a `proceed`/`retry`/`escalate_skip` next action. |
| `commit_lint(branch, project_root, require_scope=False)` | Ticket/SDLC (delivery) | Lints every commit on `branch` not reachable from `main` against conventional-commit format; each failing commit is one `GateError` (`file` = short SHA). |
| `spec_load(spec_id, project_root)` | Spec/build | Executes `.harness/specs/<id>.py` in a sandboxed namespace with a fake `harness` module injected, returns `Spec.to_dict()` (with a back-compat fallback to a `metadata` sub-dict for older spec shapes). |
| `context_fetch(reference_files, target_file, project_root)` | Spec/build | Concatenates reference-file contents (50KB truncation each) plus a directory listing adjacent to `target_file`. Returns a plain string, not JSON. |
| `artifact(action, project_root, run_id, spec_id, implementation, tests, outcome, attempts, gate_results, notes)` | Spec/build | `save`/`load`/`escalate` CRUD over `.harness/results/<run_id>.json`. `save` generates `run_id` as `<spec_id>-<timestamp>`. |
| `repair_run(run_id, diff, language, project_root)` | Spec/build | Applies a unified diff server-side (via the `patch` CLI, no shell) to a stored artifact's implementation, re-runs the gate suite, updates the artifact. Returns `{"error": ..., "fallback": "rewrite"}` if the patch itself fails to apply. |
| `memory(action, project_root, errors_text, gate, spec_id, attempt, outcome, limit=3, resolution, target_file, description, language)` | Both | `record`/`retrieve`/`gotchas` against the BM25 failure memory — see below. |
| `dag_load(task_id, project_root)` | Spec/build | Executes `.harness/tasks/<id>.py`, validates via `DAGResolver`, returns `{"task_id", "description", "layers"}`. |
| `checkpoint(action, task_id, project_root, completed=None)` | Spec/build | `read`/`write` progress checkpoints, fingerprinted per spec/task file by sha256 so an edited spec invalidates its cached progress; legacy checkpoints without a hash are treated as fully invalidated. |
| `harness_status(project_root)` | Spec/build | Lists the last 20 runs from `.harness/results/`. Returns plain text, not JSON. |
| `doctor(project_root="")` | Both | Wraps `gates.doctor.run_doctor` — probes every detected language's required tools (`<tool> --version`, 5s timeout each), returns `{"output": str, "any_missing": bool}`. |

**A naming gotcha worth knowing:** `context_fetch` (the MCP tool above) and `context_rank.py` (a separate root module, *not* exposed as an MCP tool — see below) are two unrelated things with confusingly similar names. `context_rank.py`'s own docstring calls this out explicitly to prevent conflating them.

---

## Core data models (`models.py`)

- **`StackName`** — a string enum: `python` / `typescript` / `go` / `rust`, in canonical order.
- **`GateError`** — `message, file, line, column, code, severity`.
- **`GateResult`** — `gate, passed, errors: list[GateError], duration_ms, skipped=False, skip_reason="", mode=None, baseline_excluded=[]`. Its `to_dict()` only emits the `skipped`/`skip_reason`/`mode`/`baseline_excluded` keys when they're non-default, so JSON output for callers written before those features stays byte-identical.
- **`LanguageResult`** — `language: StackName, results: list[GateResult]`, the polyglot aggregation wrapper `gate_run_on_dir` returns per detected stack.
- **`Spec`** — `id, description, constraints, acceptance_criteria, target_file, reference_files, language, metadata`.
- **`Task`** / **`TaskSpec`** — `Task(id, description, specs: list[TaskSpec])`, `TaskSpec(spec_id, depends_on)`.

---

## Memory subsystem (`memory.py`)

A single SQLite table, `failure_records(id, spec_id, gate, errors_text, tokens_json, outcome, attempt, timestamp, resolution, target_file)`, indexed on `gate`. The `resolution` and `target_file` columns were added later via idempotent, race-safe `ALTER TABLE` migrations, so an older database self-upgrades on first use even under a concurrent autopilot process.

The tokenizer lowercases text, splits camelCase, and regex-matches error codes (`ts2345`, `b105`), identifiers, and multi-digit numbers — tuned for matching compiler/linter error text, not natural language. Ranking is a from-scratch `BM25Index` (K1=1.5, B=0.75), no external search library.

Three actions, two directions:

- **`record`** — id = `sha256(spec_id:attempt:gate:errors_text[:200])[:16]`; upserts.
- **`retrieve` → `retrieve_similar(errors_text, gate, limit=3)`** — reactive, fired inside the repair loop after a gate fails. Pulls the 300 most recent rows for that gate, BM25-ranks against `"gate:<gate> <errors_text>"`, returns narrative strings that include the stored `resolution` when present.
- **`gotchas` → `retrieve_gotchas(target_file, description, language, limit=3)`** — proactive, fired *before* generation. Fences to `outcome='passed'` rows whose gate belongs to the target language's gate set, ranks by proximity tier (exact file, then same directory, then elsewhere) with BM25 over the description as a tiebreaker.

Both directions read the same opaque trail; neither ever writes to the lead-curated `_learnings.md` or `_standards.md`.

---

## DAG subsystem (`dag.py`)

`DAGResolver.validate(task)` checks that every `depends_on` reference resolves to a known `spec_id` within the same task, then runs a DFS cycle check with recursion-stack tracking. `execution_layers(task)` applies Kahn's algorithm (in-degree counting + queue) to produce `list[list[spec_id]]`, where every spec in a layer can run in parallel once all prior layers have passed.

---

## Supporting root modules

These aren't MCP tools — they're imported directly by flow procedures, hooks, or `ticket.py`'s CLI entry point.

- **`ticket.py`** — the ticket state machine's Python backbone, and a de facto CLI (`python3 ticket.py set-status ...`, invoked directly from flow docs). Key functions: `claim()` (ledger-coordinated, push-first-wins number assignment with file-lock + retry), `deliver_commit` / `deliver_publish` / `deliver_squash` / `deliver_squash_batch` (squash-merge, archive, ledger event), `cancel` / `abandon` / `reopen` / `migrate`, plus a private atomic ticket-lock implementation (`O_CREAT|O_EXCL`, staleness detection via PID liveness).
- **`ticket_deps.py`** — the `depends-on:` graph layer: `build_graph`, `check_cycle`/`assert_acyclic`, `topo_layers` (Kahn), `mermaid_diagram`, and `assert_acyclic_with_proposed` (overlays an about-to-be-written ticket onto the loaded graph before checking, so a cycle introduced by the edge being authored is caught before it's persisted).
- **`ticket_templates.py`** — pure library backing `/problem`'s templating: `infer_category` (keyword heuristic), `load_template` (per-category templates), `load_custom_sections`/`merge_sections` (lead-defined sections from `_standards.md`), `enforce_line_limit`.
- **`audit.py`** — `record(action, ticket, detail, root)` appends one JSON line to `.harness/audit.log` via a single atomic `os.write()` on an append-only fd. Identity resolution falls back `git config user.name` → `$USER` → `getpass.getuser()` → `"unknown"`, fail-open by design — a logging failure must never look like the real operation failed.
- **`health.py`** — the read-only dashboard behind `/health`. Scans `gate-findings.md` files across tickets, computes pass rates and trend indicators per gate, and queries `memory.db` read-only for average repair cycles and top failure modes. Validates `project_root` containment before any I/O.
- **`flaky_detect.py`** — re-runs the pytest suite N times, diffs per-test pass/fail across runs to identify non-determinism, writes `.harness/flaky-report.json`/`.md`. The failure-annotation consumer (`annotate_failures`) fails closed — treats a missing or malformed report as a hard blocker rather than assuming no flakiness. Pytest-specific; no Go/Rust/TypeScript equivalent exists.
- **`learnings.py`** — shared mechanics for `/deliver` and `/harvest-learnings`: `parse_findings` (extracts from `gate-findings.md`/`critic-findings.md`), `sanitize_pattern` (strips non-directive or attacker-influenceable text), `dedupe_candidates`, `append_learnings` (writes only validated template fields — `date | gate | ticket | pattern` — never raw extracted text, never overwriting existing content).
- **`panel_detect.py`** — the deterministic panel-activation engine. Reads `context/panels/triggers.md`, matches file globs and manifest dependency names (parsing `package.json`/`pyproject.toml`/`go.mod`/etc. directly) to decide which expert panels activate for a given scope; outputs `active`/`candidates`/`skipped`.
- **`context_rank.py`** — the ticket-0076 local context assembler: batches a single `rg -Fn` call across up to 40 query terms, ranks files by distinct-term overlap, extracts small windows around the best-matching line per file, and caps the total pack at 200 lines. `get_or_generate_pack` is the sole I/O boundary, caching under `.harness/context/<ticket>.md` keyed by a hash of the query plus git HEAD plus working-tree status — so an uncommitted repair-round edit correctly invalidates a same-HEAD cache. Not the same tool as the `context_fetch` MCP tool above.
- **`dry_run.py`** — the deterministic core of `/build --dry-run`: flag parsing, the ticket-mode-only guard, plan assembly, and a sandboxed gate runner that owns and always cleans up its own temp directory.
- **`sarif_output.py`** — `build_sarif(results, worktree_root)` maps `GateResult`s to a deterministic SARIF 2.1.0 document (no timestamps or UUIDs, so output is reproducible); `write_sarif` writes atomically. Deliberately named `sarif_output`, not `sarif`, to avoid shadowing the `sarif-tools` package's own module of that name.
- **`spec_coverage.py`** — matches `requirements.md`'s functional requirements and acceptance criteria against a ticket's spec files by token-overlap (Jaccard), parsing specs via `ast` — it never executes them, unlike `spec_load` above, which does exec specs inside a sandboxed namespace. Writes a non-blocking `spec-coverage.md` warning.
- **`mode_branch.py`** — trivial but load-bearing: `is_autopilot_mode(mode)` is an exact string match against `"autopilot"`, fail-closed (defaults to `False`) so an unrecognized mode value is never accidentally treated as autopilot.
- **`validators/`** — `standards_validator.py` and `score_spec.py`, the standards-file and spec-scoring validation logic invoked by `/problem`'s Phase 6 score-spec pass and elsewhere.

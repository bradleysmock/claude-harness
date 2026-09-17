# Gates and Hooks

Part 2 of the design series. See [00-overview.md](00-overview.md) for the philosophy behind this layer ("deterministic authority lives in Python") and [03-mcp-server.md](03-mcp-server.md) for how gates are exposed as MCP tools. This document covers the mechanical enforcement layer in full: what runs when, what each gate actually checks, and the anti-cheat machinery that keeps a repair loop honest.

---

## Hook registration

Five hooks are wired in `.claude-plugin/plugin.json`, all invoked as `python3 <hook>.py` — no venv, stdlib + local modules only, so they run even before the MCP server's first bootstrap completes:

| Claude Code event | Hook(s), in order | Blocks the action? |
|---|---|---|
| `PreToolUse` (Write\|Edit\|MultiEdit) | `pre_ticket_diff.py`, then `pre_write_guard.py` | `pre_ticket_diff`: never. `pre_write_guard`: yes, on a forbidden pattern |
| `PostToolUse` (Write\|Edit\|MultiEdit) | `post_write_gate.py` | No — reports findings, doesn't block |
| `Stop` | `stop_full_gate.py`, then `ticket_commit_guard.py` | Both can block the turn (exit 2) |

All hooks that also touch gate logic import from the shared `gates/` package — one canonical implementation, never triplicated across hook / MCP tool / flow doc. A drift test (`tests/test_0052_hook_gate_drift.py`) parses `harness-reference.md`'s hook↔MCP command table and asserts the documented commands still match both the hook source and the gate source, so a hook and the full MCP gate can never silently diverge on what "passing" means for the same language.

### `pre_write_guard.py` — blocks forbidden code shapes

Runs **before** the write lands. Scans the incoming content fragment for hard-banned patterns: `eval`/`exec`/`Function()`/`pickle.loads` on external input, `shell=True`, string-interpolated SQL, hardcoded credentials. A match blocks the write outright — this is the one hook that prevents bad code from ever touching disk, rather than catching it after the fact.

### `post_write_gate.py` — per-file lint + SAST

Runs after every Write/Edit. Resolves the tool for the written file's language and project root (e.g. `eslint` via `npx --no-install` from the nearest `package.json`, matching how the Stop hook resolves it — see the parity table below) and returns structured `file:line` findings. Fast, per-file feedback; doesn't run the full suite.

### `stop_full_gate.py` — full suite at turn end

Runs the complete gate suite (lint → type-check → tests → security) against a worktree, but **only** when that worktree's ticket is `review-ready` — it doesn't fire on every turn of every ticket, just the ones claiming to be done. Blocks the turn on any failure. Also loads `gates/repair_integrity.py`'s `SUPPRESSION_MARKERS` table directly by file path (not via the full gate-suite import) specifically so the marker list used to flag bare suppressions can never drift out of sync with the craft-polish pass's own check.

### `pre_ticket_diff.py` — display-only, never blocks

Before a Write/Edit/MultiEdit to an existing, non-empty `.tickets/**/*.md` file, prints a unified diff of the pending change to stderr so the operator can see exactly what a flow (most often `/refine`) is about to overwrite. Reconstructs the proposed content in-process — replays `Write`'s content directly, or replays `Edit`/`MultiEdit`'s `old_string`→`new_string` patches sequentially onto the current file — and diffs with `difflib`, no subprocess. Every failure path (missing file, unreadable, non-UTF-8, an `old_string` that wouldn't actually match, or the `HARNESS_NO_DIFF=1` override) exits 0 silently; this hook exists purely for visibility, so any uncertainty means "say nothing" rather than "block."

### `ticket_commit_guard.py` — blocks on uncommitted ticket state

The multi-developer safety net. Blocks turn-end (exit 2) if either condition holds:

- **Dirty ticket files.** Discovers every checkout — the main root plus every worktree, via `git rev-parse --git-common-dir` then `git worktree list --porcelain`, with all paths resolved to a canonical form to dodge macOS's `/private/var` vs `/var` aliasing — and runs `git status --porcelain -- .tickets/` in each independently. A branch-only ticket directory that doesn't exist on `main` is correctly never flagged, because `main`'s own status check simply has nothing to report for it. Ignores the lock file, the active-ticket pointer, and stale-lock steal artifacts.
- **Unpushed ledger commits.** A local `harness-tickets` commit not yet present on `origin/harness-tickets` is a claim or transition that reserves nothing until it's published — the guard blocks rather than let the session end with an unpublished number reservation that would race the next writer.

Both conditions can fire in the same run, and the guard prints separate, specific remediation instructions for each.

---

## Gate suites by language

Gates run in one of two modes. **Directory mode** validates a real worktree with full project context (used by `stop_full_gate` and the `gate_run_on_dir` MCP tool — the ticket/SDLC path). **Text mode** validates generated code in isolation, no project context (used by `gate_run` — the standalone spec/build path). Each suite is fail-fast: the first failure stops the run.

| Language | Directory mode | Text mode |
|---|---|---|
| Python | lint → type_check → tests → security | syntax → type_check → lint → tests → security |
| TypeScript | type_check → lint → tests | type_check → lint → tests |
| Go | build → vet → tests | build → vet → staticcheck → tests |
| Rust | check → clippy → tests | check → clippy → tests → audit |

### Hook ↔ MCP gate command parity

The write-time hooks and the full MCP gate run must invoke the *same* commands per language, or the same code could pass one and fail the other:

| Language | Per-write hook | Stop hook | MCP gate |
|---|---|---|---|
| Python | `ruff check`, `bandit -ll` | + `mypy`, `pytest -q` | `ruff`, `mypy`, `bandit`, `pytest` |
| JS/TS | `npx --no-install eslint` | + `npx --no-install tsc --noEmit`, `npm test` | `eslint`, `tsc --noEmit` |
| Go | `gofmt -l` | + `go vet ./...`, `go test -race ./...` | `go vet`, `go test -race -v ./...` |
| Rust | `rustfmt --check` | + `cargo clippy`, `cargo test` | `cargo check`, `cargo clippy`, `cargo test` |

The Go row is the parity case that motivated this table in the first place: both the Stop hook and the MCP gate run `go test -race`, so a data race can't slip past one layer and fail the other.

### Baseline-delta testing (all four languages)

In directory mode, the `test` phase runs the **entire** suite but fails only on tests not already failing at the merge base. It collects stable per-test IDs (`path::test`, `pkg.TestName`, `crate::mod::test`), computes the baseline once per merge-base SHA in a throwaway detached `git worktree` (cached under `.harness/test-baselines/<sha>.json`), and subtracts it. What remains gates the ticket; pre-existing failures are reported as `baseline_excluded` (informational). A previously-passing test that's deleted in the worktree (`pass→removed`) is flagged as a regression too. No git or no resolvable merge base → strict full-suite fallback, fail-closed. The shared engine is `gates/_baseline.py`, applied uniformly across languages so an unrelated already-red test in one language never blocks a polyglot ticket while being tolerated in another.

### The SAST phase

Runs last in directory mode, after the language suite and the coverage/dep-audit phases. Composed from five files:

- **`sast_models.py`** — the shared model, deliberately separate from `models.GateError` because SAST needs a tiered severity. `Finding(file, line, rule_id, severity, message, tool)`; `map_severity(tool, native)` normalizes each tool's native severity (Semgrep `ERROR`/`WARNING`/`INFO`, Bandit `HIGH`/`MEDIUM`/`LOW`) to `BLOCKER`/`MAJOR`/`MINOR` — an unrecognized value degrades to `MINOR`, never gets silently promoted.
- **`sast_util.py`** — shared helpers: `tool_available` (checks both a PATH binary and an importable module, since Bandit ships as a Python module), `resolve_contained` (project-owned config discovery with symlink-safe containment), `relativize` (worktree-relative paths, `None` if a tool-reported path escapes).
- **`sast_bandit.py`** — runs only if `.py` files exist. The core subtlety: Bandit exits 1 both for "findings present" and for some invocation faults, so the JSON body is validated (`results` key present) to disambiguate — an unparseable exit-1 is an `invocation_error`, fails closed, never read as clean.
- **`sast_semgrep.py`** — prefers a project-owned `.semgrep.yml` (containment-checked), else falls back to `p/default` with a floating-ruleset warning. Even on a "clean" exit-1, it inspects Semgrep's own `errors` array for `level=="error"` entries — a populated array means the scan is untrustworthy regardless of exit code, and is treated as an invocation error.
- **`sast.py`** — the orchestrator (`run_sast_gate`). Runs both adapters, aggregates: HIGH/`ERROR` → BLOCKER fails the gate; MEDIUM/LOW → non-blocking warnings. Both tools unavailable → single "SAST skipped" pass-with-warning. Writes an idempotent `# SAST — gate-findings` section to `gate-findings.md`.

**Known limitation:** because the directory suite is fail-fast and SAST runs last, a failing lint/type/test phase short-circuits the run before SAST executes. Fix earlier-phase failures first to surface SAST findings.

---

## Individual gate modules

### `red_gate.py` — TDD enforcement, mechanically

Backs the `gate_run_red_check` MCP tool. Given a spec's newly-written test(s), runs *only* those tests (exact node-id filter — never the full suite) against the pre-implementation worktree and classifies the result: `RED` (fails as expected — proceed), `BLOCKING` (already passes — not discriminating, must be revised), `TOOL_ERROR` (inconclusive — never conflated with RED). The classifier specifically checks for an import/module-not-found marker before defaulting to `TOOL_ERROR`, so "can't import the not-yet-created module" is legitimately `RED`, not a tool fault. `next_action(classification, attempt, max_attempts)` is a pure decision function: `TOOL_ERROR` always escalates immediately without consuming a retry; `BLOCKING` retries until budget exhaustion. This is what makes "write the test first" an enforced precondition rather than a convention — `/build` calls this before writing any implementation for a spec.

### `commit_lint.py` — conventional-commit enforcement

Validates every commit on a delivery branch (not reachable from `main`) against `type(scope): subject`, pure Python, no external commitlint dependency. The allowed-types list includes `polish` specifically so the craft-polish pass's own `polish: craft round N` commits pass the same check it enforces on everyone else. Overridable via a `## Commit Lint` block in `_standards.md`. Security-hardened: branch/ref names are allow-listed before reaching `git` (blocks option-injection via a leading `-`), an unresolvable base branch fails closed (`BASE_BRANCH_UNKNOWN`) rather than silently passing, and subjects are truncated before regex matching to bound backtracking cost. Exposed as the `commit_lint` MCP tool and run as a `/deliver` preflight step through the promotion-policy engine.

### `doctor.py` — tool-availability diagnostics, read-only

Backs `/doctor` and the `doctor` MCP tool. Builds its required-tool list per language directly from each gate module's own `REQUIRED_TOOLS` export, so the diagnostic can never drift from what the gates actually invoke. Probes mirror exactly how each gate resolves a tool — a bare PATH binary, `python -m <tool>`, or `npx --no-install <tool>` — so, for example, `cargo clippy` is probed as the `cargo-clippy` shim, not a nonexistent bare `clippy`. Statuses: `FOUND`, `FOUND_ERROR` (binary present but exits non-zero), `MISSING`, `TIMEOUT` (5s budget per probe). Never modifies anything — suitable as a CI preflight.

### `coverage.py` — coverage-threshold enforcement

Wraps pytest-cov, nyc/c8, and cargo-llvm-cov behind one interface. Thresholds come from `.tickets/_thresholds.yaml`; an absent file skips enforcement, malformed YAML skips with a warning — but a tool that ran and produced output Python can't parse is a hard fail (`COVERAGE_PARSE_ERROR`), because "no parseable number" must never be read as "coverage is fine." Base-branch coverage for delta comparison is measured in a non-destructive detached `git worktree` at the merge-base SHA, always cleaned up in a `finally`; if that worktree's own coverage run fails, delta assumes `0.0` (no regression) rather than blocking on an unrelated infra hiccup. Writes both a `gate-findings.json` sidecar and a markdown section, scoped to the *active ticket directory* — this is the gate `/deliver`'s coverage preflight reads.

### `dep_audit.py` — dependency vulnerability scanning

Ecosystem-aware: `npm audit`, `pip-audit`, `cargo-audit`, `govulncheck`. When multiple manifests are present, Node.js is checked first and every detected manifest is named in a warning. Uses its own local `GateError`/`GateResult` shapes (uppercase `BLOCKER`/`WARNING`, deliberately decoupled from the language-gate shape) with a configurable severity threshold and an ignore list validated against advisory-ID patterns (GHSA/CVE/RUSTSEC/GO). `govulncheck`'s output is schema-versioned against a known-tested set — an unrecognized schema version is a warning rather than a guessed partial parse, because Go's JSON format here is explicitly unstable. The enable check (`dep_audit_enabled`) fails **open**: a broken config can never silently disable this security gate. Writes findings to a top-level `gate-findings.md` (project root, not the ticket directory).

### `secrets.py` — credential scanning

Prefers gitleaks, falls back to trufflehog, and fails closed with neither installed (override: `HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1`). The load-bearing discipline here is that raw secret text never reaches a `GateError` or `gate-findings.md` — only structural fields (rule ID, file, line) are read from scanner output; `Match`/`Secret`/`Context` fields are never touched. `_redact()` renders a fixed-length mask (`<rule> @ <file>:<line> (<first4>****)`) so even the credential's true length is never leaked. Every scanner-reported path is containment-checked before being surfaced. Note the gitleaks precondition: it scans committed history, so uncommitted content needs a separate pass — a documented gap, not a bug.

---

## Critic-findings machinery

Findings need a stable identity across repair rounds even though the critic agent itself has no memory between spawns. Six small modules make that work:

- **`finding.py`** — the shared model: `Finding(file, line, severity, code, message)`. `finding_key(f)` returns `(file, line, severity, code)` — deliberately message-independent, since a rephrased description of the same issue must still count as the same finding.
- **`finding_parser.py`** — parses `gate-findings.md`'s mechanical grammar (`` - `file:line` [code]: message ``), defaulting severity to `MAJOR` since gate findings carry no explicit tier.
- **`critic_finding_parser.py`** — parses critic *prose* in two supported grammars: the `## Finding Table` markdown table (from the `critique` skill), and the `**SEVERITY** · Panel/Dimension · \`file:line\`` header block (from `critic-brief.md`). `code` is populated from the Panel/Dimension label — a stable structural discriminator — so two distinct findings at the same `file:line:severity` don't collide.
- **`critic_reconciler.py`** — `reconcile(prev, curr)` classifies findings across a repair round as fixed / persisted / new, filtered to BLOCKER/MAJOR only (MINOR/OBS never enter reconciliation). Round-to-round identity is carried entirely through hidden markers embedded in the persisted `critic-findings.md` file (`<!-- harness-finding-key file:line:severity:code -->`) rather than any in-memory state — `latest_section()` returns only the most recent `##`-headed section, so a key that persisted across multiple rounds is never double-counted.
- **`incremental_scope.py`** — supports round-2+ critic spawns getting a diff-scoped brief instead of a full-worktree re-read. `touched_files_from_diff()` is a pure, containment-checked diff parser handling add/modify/delete/rename; `format_incremental_brief()` renders prior BLOCKER/MAJOR findings plus the round's raw diff into a deterministic brief.
- **`repair_integrity.py`** — the anti-cheat guard, classifying a repair diff for three violation shapes: net-removed test *definitions*, added skip/xfail/ignore markers, and bare suppression pragmas (a `# noqa`/`# type: ignore`/etc. with no reason on an added line — any trailing text counts as "explained"; adequacy is left to human/critic review). `SUPPRESSION_MARKERS` is a single named table imported both here and directly by `stop_full_gate.py` by file path, so the two call sites can never drift on what counts as a suppression. A known, accepted gap: a same-file "balanced swap" of a real test for a trivial one isn't caught here — that's left to the critic's dedicated weakened-tests check.

---

## PR-comment integration

`gates/pr_detector.py`, `comment_deduplicator.py`, and `pr_commenter.py` implement GitHub PR review-comment posting, gated behind `gh` CLI availability. `detect_pr()` probes auth and PR state without ever logging token output. Deduplication hashes each finding (`file:line:message` for gates, `file:line:severity:code` for critic findings, since critic prose isn't deterministic) and embeds the hash as a hidden marker in the posted comment body — later runs re-fetch existing comments, harvest the markers back out, and never re-post. `post_findings()` routes each finding to an inline (in-diff) or top-level (off-diff, or no location) comment, collapsing an oversized batch entirely to top-level; every failure mode (missing `gh`, not authenticated, no open PR, dedup-fetch failure) falls back to printing findings to the terminal rather than losing them.

---

## Scheduling, policy, and pluggable gates

### Parallel gate scheduler

In directory mode, independent gates run concurrently on a thread pool (`gates/scheduler.py`); a gate with a declared prerequisite (`gates/gate_graph.py` — `test` depends on `type_check`/`build`/`check`) waits for it. Opt-in per project via `parallel_gate_limit = N` in `_standards.md`'s `[gates]` block; absent the key, execution stays sequential. A failed prerequisite marks its dependent `SKIPPED`, not silently passed. Under fail-fast, a gate failure stops *new* submissions but lets in-flight gates finish. `gates/_scope.py` compiles each gate's file-scope glob (fast-pathing plain suffix/filename matches, falling back to `PurePosixPath.match` only for genuinely complex globs) so the scheduler can skip a gate whose scope doesn't intersect the changed files. `gates/log_writer.py` writes each gate's full, untruncated output to `<log_dir>/<gate>.log` on completion, with the gate name structurally validated as a safe path component before any file is touched.

### Data-driven promotion policy

`gates/policy.py` centralizes "which gates block, and what happens when one fails" into one declarative table plus one pure evaluator (`evaluate_promotion`), replacing an earlier hardcoded assumption that every gate is required and any failure blocks. Configured via a `[policy]` sub-block in `_standards.md`'s `[gates]` fence, keyed `<language>.<gate>.<field>` or `global.<gate>.<field>`. `outcome` is `"promote"` / `"block"` / `"pause_for_human"` — the worst severity across all required gates; `blocking_gates` omits a failure whose declared dependency also failed, presumed a downstream symptom rather than an independent problem. No `[policy]` block reproduces the original behavior exactly (every gate required, `on_block="fail"`).

### Pluggable external gates (SARIF-in)

An `[external_gates]` sub-block lets `_standards.md` declare an already-installed subprocess whose stdout is SARIF 2.1.0 as a gate, with no new `gates/*.py` module required — parsed fail-closed, a name colliding with any built-in gate is a `CONFIG_ERROR`. Ingestion mirrors `sarif_output.py`'s path-containment discipline on the way in: an escaping `physicalLocation` becomes `file=None` rather than passing through raw, and a `results` array over 500 entries (or invalid/absent SARIF) is a `TOOL_ERROR` — a non-zero exit alone is never sufficient, since many scanners exit non-zero simply because they found something.

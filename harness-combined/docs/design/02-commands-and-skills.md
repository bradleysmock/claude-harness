# Commands and Skills

Part 3 of the design series. See [00-overview.md](00-overview.md) for the pipeline these drive and [01-gates-and-hooks.md](01-gates-and-hooks.md) for what happens underneath every gate/repair reference below.

Claude Code auto-discovers `commands/` (explicit `/name` invocations) and `skills/` (intent-triggered — the model picks the skill from its description, though most also have a `/name` command that thinly dispatches to them). This document catalogs all 30 commands, all 11 skills, and the three subagent definitions, then covers the expert-panel system that the critic and `critique` skill share.

---

## Command catalog

### Design phase

| Command | Purpose |
|---|---|
| `/problem <description>` | Entry point for new work. Phase 0 clarity check (asks only if user/outcome/scope is genuinely missing) → claims a ticket number off the `harness-tickets` ledger → creates branch + worktree → writes `problem.md` → `requirements.md` → a stack-advisor sub-flow (new-app/service/UI detection only) → `solution.md` (with a dependency-cycle check before persisting any `depends-on:`) → design-phase critic loop (max 2 rounds) → a score-spec validation pass → **Checkpoint 1**. All writes land on the branch, never `main`. |
| `/requirements [XXXX]`, `/solution [XXXX]` | Manual escape hatches for individual `/problem` phases. |
| `/refine [XXXX]` | Interactive solution refinement. Also has a non-interactive **autopilot mode**, entered only from the autopilot flow, that makes at most one bounded revision pass to clear a semantic score-spec block — deriving fixes only from existing artifact text, never inventing scope. |
| `/replan XXXX` | Regenerates `solution.md` from scratch from `problem.md` + `requirements.md` (distinct from `/refine`'s in-place edit). Snapshots the old solution, warns if a worktree with in-progress work already exists, runs the same critic loop as `/problem` Phase 5, and can roll status back from `implementing`/`review-ready`/`changes-requested` to `solution`. |
| `/requirements-review XXXX` | Thin wrapper for the `requirements-review` skill. |

### Build phase

| Command | Purpose |
|---|---|
| `/write-spec <arg>` | **Optional** pre-step. Dispatches on argument shape: a 4-digit-prefixed arg routes to the ticket flow, free-form text routes to the spec flow (which explores the codebase first). `/build` self-generates specs when absent, so this exists only to pre-generate or hand-tune one. |
| `/build <arg> [--dry-run]` | Single entry point for implementation. Mode-dispatches to the ticket flow (worktree + diff) or the spec flow (temp dir + artifact); `--dry-run` is ticket-mode only and rejected in spec mode. |
| `/deliver <arg> [--pr]` | Single entry point for shipping. Mode-dispatches to merge-and-cleanup (ticket) or write-artifact-to-target (spec). `--pr` (ticket mode only) pushes the branch and opens a GitHub PR via `gh` before the local squash-merge. |

Each of these three is a thin controller: it inspects the argument, decides ticket vs. spec mode, and loads exactly one `context/flows/<command>-<mode>.md` file — keeping per-invocation context lean and the user-facing surface to one command per concept.

### Autopilot family

| Command | Purpose |
|---|---|
| `/autopilot XXXX [YYYY ...]` | Fully autonomous pipeline, requires `status: solution`. A single ID runs the full build→deliver flow unattended, pausing only for a genuine block: spec-remediation exhaustion, repair-loop exhaustion, or a scope-drift confirmation forced by a mid-build `/refine` touch. Two or more IDs run **batch mode**: all members build into one shared integration worktree, one combined critic reviews the union, and delivery is atomic — one push containing a separately-squashed commit per member, with no partial delivery if repair is exhausted on any one of them. |
| `/autopilot-watch start\|stop\|status [--interval N]` | A standalone background process, independent of any Claude session, that polls for `status: solution` plus a content-diff-verified `approved-commit` (rejecting any ticket whose design files have drifted since approval) and dispatches `/autopilot XXXX` automatically — default 30s interval, one dispatch in flight at a time. `status` reports PID, last tick, last outcome, and a needs-attention count; failures/timeouts are appended to a JSONL log and trigger a best-effort desktop notification. |

### Maintenance and operations

| Command | Purpose |
|---|---|
| `/gate XXXX` | Manual full gate run → `gate-findings.md`, with changed-file scoping, flaky-test annotation, promotion-policy evaluation, optional SARIF emission, and optional `--comment` to post inline GitHub PR review comments. |
| `/doctor [project_root]` | Read-only per-language tool-availability probe; useful as a CI preflight. |
| `/flaky [--runs N] [--threshold T]` | Re-runs the test suite N times (default 5), flags tests with mixed pass/fail outcomes across runs, writes `.harness/flaky-report.json`/`.md`. Feeds `/gate`'s failure-annotation step. Pytest-specific today — no Go/Rust/TS equivalent exists yet. |
| `/health` | Read-only cross-ticket dashboard: gate pass rates over recent builds, average repair cycles, top recurring error codes, worst-performing tickets, per-gate trend indicators. Also exists as the `health` skill — same implementation, either trigger. |
| `/harvest-learnings [gate-filter]` | Mines `.harness/memory.db` for **recurring** (2+ occurrence) cross-ticket failure patterns and appends lead-approved entries to `_learnings.md`. The always-available capture path, complementing `/deliver`'s opportunistic per-ticket capture (which only fires when a ticket has its own `gate-findings.md`). |
| `/milestone [name]` | Read-only roll-up of tickets against named milestones declared in `.tickets/_milestones.md`. |
| `/ticket-list [--open\|--completed] [--status S] [--milestone M]` | A flat table of every ticket, unioning the ledger (for in-flight discovery) with a `.tickets/*` scan (local fallback). |
| `/ticket-status` | Distinct from `/ticket-list`: additionally computes an implementation-order/wave plan and a dependency Mermaid graph. |
| `/export [--format json\|csv] [--all] [--output file]` | Exports ticket metadata + commit history to JSON/CSV for external tooling. |
| `/changelog` | Generates/refreshes `CHANGELOG.md`'s `## [Unreleased]` section from completed tickets and conventional commits since the last tag. Idempotent replace-in-place, sanitizes titles against Markdown-heading injection. |
| `/velocity` | Cycle-time report (start = `problem.md` date, done = `status.md updated:`). Deterministic date math is delegated to `skills/velocity/compute.py`, but the surrounding procedure lives directly in the command file — there's no `skills/velocity/SKILL.md`, unlike `/sprint` below. |
| `/sprint [--sprint-capacity N] [--max-sprints N] [--as-of DATE]` | Dependency-ordered, capacity-bounded weekly sprint plan. A pure pass-through to the `sprint` skill — the command file has no logic of its own, unlike `/velocity`. |
| `/bisect --good <ticket\|ref> [--bad ref] [--run cmd]` | Ticket-aware `git bisect`: resolves ticket numbers to their delivery merge commits, wraps multi-word test commands in a temp script, and attributes the culprit commit back to the ticket that introduced it via merge-ancestry traversal. |

### Ticket-state transitions

| Command | Purpose |
|---|---|
| `/cancel XXXX [--abandon]` | Main-free: appends `cancelled` (or `abandoned`) to the ledger, archives docs onto `harness-tickets`, deletes the worktree and branch. |
| `/abandon XXXX` | A dedicated alias for `/cancel --abandon` — work started but dropped, as distinct from a deliberate cancellation. |
| `/reopen XXXX` | Forks a fresh branch from `main` HEAD for a terminal ticket, restores the archived directory, sets `status: solution`, appends a `reopened` ledger event. Warns and stops if a partial-reopen worktree already exists. |
| `/rollback XXXX [--dry-run]` | Reverts a delivered ticket's squash-merge commit via `git revert` (never `git reset`). A thin wrapper for the `rollback` skill; see below for the full fail-closed procedure. |
| `/init` | Scaffolds `.harness/`, `.tickets/`, `.worktrees/`, gitignore entries, `.harness/config.py`, bootstraps the `harness-tickets` ledger branch (or migrates a pre-ledger project), and writes `_standards.md`/`_learnings.md` stubs (skip-if-exists). |
| `/suggest`, `/usage-report [args]` | Thin command wrappers for the `suggest` and `usage-report` skills. |

---

## Skill catalog

Skills are triggered either explicitly (`/<name>`) or by describing the intent in conversation — the model matches against the skill's description.

| Skill | Purpose |
|---|---|
| **`suggest`** | Detects harness-plugin-root vs. app-project mode, inventories current capabilities (commands/skills/gates, or stack/README/structure), reads open ticket titles inside an explicit trust boundary, and surfaces up to 10 deduplicated improvement ideas with `/problem`-ready lines on acceptance. |
| **`review`** | Interactive, panel-aware post-build review — the conversational twin of the automatic post-build critic: same panels, same checks, but streamed with follow-up capability. Sets `changes-requested` on any BLOCKER; records an audit `resolve-pause` event if it clears a prior pause. |
| **`critique`** | Free-form expert-panel critique of any scope — files, globs, a git ref, or a keyword; asks if given nothing. Writes the full report to `.harness/critiques/<date>-<NN>-<slug>.md` (anchored at the main repo root, never inside a worktree) and shows a compact summary in the terminal. Has a design-artifact mode for RFC-style review of `problem.md`/`requirements.md`/`solution.md`. Not ticket-scoped, and adds a Codebase Patterns section the ticket-scoped `review` skill doesn't have. |
| **`status`** | Combined dashboard: active/completed tickets (ledger-primary, worktree-aware), a stale-ticket summary, spec/build run status, failure-memory presence, and the three most recent critiques. |
| **`stale`** | Lists tickets whose `updated:` field exceeds a threshold (default 7 days, configurable, capped at 365). Uses strict date parsing — malformed dates are skipped, never guessed — and surfaces a degraded-confidence warning if more than a quarter of tickets were skipped. |
| **`health`** | Same implementation as `/health` above. |
| **`sprint`** | See `/sprint` above — the actual logic lives here; deterministic, reads ticket data over stdin, aborts with no partial plan on a dependency cycle. |
| **`rollback`** | The logic behind `/rollback`. Twelve fail-closed steps: validate the ticket number → resolve `status.md` (rejecting a simultaneous active-and-completed "partial archive" state as ambiguous) → require `status: done` → find the exactly-one merge commit for the ticket → dry-run short-circuit → confirm with the lead → clean-tree preflight → `git revert --no-commit -m 1` → commit with a fixed message format → audit record. Never touches `git reset`. |
| **`velocity`** | See `/velocity` above. |
| **`debug`** | Classifies an escalated standalone run into one of five failure classes (spec ambiguity, missing context, environment gap, test-design flaw, or a genuinely hard problem) from the persisted artifact and critic findings, proposes a class-specific fix, and asks before applying it. |
| **`requirements-review`** | Security-hardened by design: dispatches the untrusted `problem.md`/`requirements.md` text into the scoped, read-only `requirements-analyst` subagent, so the write-capable parent session never ingests untrusted ticket content directly — closing what would otherwise be a "read sensitive + untrusted content + write capability" combination in one context. Evaluates completeness, testability, coverage, and consistency; writes an advisory `requirements-findings.md`. Never transitions ticket status. |
| **`usage-report`** | Runs a stdlib-only analyzer over local `~/.claude` state (transcripts, history, stats cache), cross-references billing mode for cache-TTL-specific advice, optionally fetches Anthropic's public roadmap, and writes a dated markdown report. Explicit "never invent metrics" discipline throughout. |

---

## Subagent definitions

All three are architecturally read-only (Read/Grep/Glob only) — the restriction lives in the agent's own tool frontmatter, not just in prompt text, so it holds even against an adversarial or malformed brief.

- **`critic`** (`agents/critic.md`) — the workhorse reviewer, delegating almost entirely to `context/critic-brief.md`. Loads the `core` panel (always active) plus additional panels resolved via `panel_detect.py` against `context/panels/triggers.md`; for code review, also reads `gate-findings.md` (never re-flags an issue the gates already caught) and evaluates ticket-baseline checks — requirements coverage, solution alignment, and a weakened/deleted-tests check, all BLOCKER-tier. Findings use the machine-parseable `**SEVERITY** · Panel/Dimension · \`file:line\`` header format consumed by `gates/critic_finding_parser.py`. Invoked at `/problem` Phase 5 (design), `/build` Step 7/7a (code — with an incremental-scope mode for repair rounds 2+), and inside `repair-escalation.md`.
- **`craft`** (`agents/craft.md`) — the post-acceptance craft reviewer. Bounded to a nine-category taxonomy (`rename | extract | inline | comment | delete | simplify | error_handling | consistency | restraint`), explicitly denied any implementer-reasoning context — the same asymmetric-exposure pattern as the critic. Returns structured JSON only; an empty `improvements` list is the convergence signal. Its claim of "behavior-preserving" is never trusted on its own — the calling flow enforces that mechanically with a gate re-run plus pinned-pre-polish-test survival (see [01-gates-and-hooks.md](01-gates-and-hooks.md)).
- **`requirements-analyst`** (`agents/requirements-analyst.md`) — single-purpose subagent behind the `requirements-review` skill, existing specifically to contain the prompt-injection surface of untrusted ticket content.

---

## Notable flow mechanics

A few things worth knowing that aren't obvious from the command/skill descriptions alone:

- **Batch autopilot excludes machine-adjusted tickets.** Any member carrying a `refine-touched` marker (meaning `/refine`'s autopilot mode touched its design mid-build) is excluded from a batch *before* the two-or-more-member check runs — batching falls back to single-ticket autopilot if only one member survives exclusion.
- **Delivery has more preflight than "run the gates."** `/deliver` runs a conventional-commit lint gate, a coverage-enforcement preflight (fail-closed on a missing or malformed coverage sidecar — never treated as "no data available"), a refine-touched confirmation (forces the lead-confirm prompt even under autopilot's normal skip-confirm behavior), a pre-deliver rebase guard against `main`, optional GitHub PR integration, and a post-merge smoke test with a configurable auto-revert-or-warn policy.
- **Dry-run build proves it writes nothing, mechanically.** `/build --dry-run` no-ops the spec-persist step, runs gates in a temp directory under `.harness/dry-run-tmp/` that's unconditionally deleted afterward, and only ever writes `gate-findings.md` inside the ticket directory — never a worktree. Its design-phase critic reviews spec metadata only, deliberately keeping raw generated code out of a tool-capable agent's context.
- **`/velocity` and `/sprint` aren't structurally parallel**, despite looking that way in the command table. `/sprint` is a pure pass-through to a skill; `/velocity` has its own procedure inline in the command file, delegating only the date arithmetic to a helper script. Don't assume one implies the pattern of the other.

---

## Expert review panels

The `critique` skill and the `critic` subagent share one panel system, loaded by file scope. Each panel names 1–3 working experts, their key positions, and hazard tables by severity. Panels are additive: a Python route handler returning an HTMX swap activates Core + Python + HTTP/API + Hypermedia + UI simultaneously, each contributing from its own lens.

| Category | Panel | Panelists | Trigger |
|---|---|---|---|
| Foundation | `core` | Martin, Parnas, Ousterhout, Fowler, Beck, McGraw, Evans, Wright (Hyrum's Law) | Always active |
| Languages | `python` | Hettinger, Beazley | `.py` files, Python project markers |
| | `typescript` | Hejlsberg, Collina | `.ts`/`.tsx`/`.js`, `package.json` |
| | `go` | Pike, Kennedy | `.go`, `go.mod` |
| | `rust` | Matsakis, Gjengset | `.rs`, `Cargo.toml` |
| | `jvm` | Goetz, Bloch | `.java`/`.kt`, Gradle/Maven |
| | `cpp` | Stroustrup, Sutter | `.c`/`.cpp`/`.h`, `CMakeLists.txt` |
| | `shell` | Wooledge, Ramey | `.sh`/`.bash`, shell shebangs |
| Frontend frameworks | `angular` | Gechev, Lesh | `@angular/core`, `angular.json` |
| | `react` | Abramov, Linsley | `react` package, JSX/TSX |
| | `vue` | Evan You, Anthony Fu | `vue` package, `.vue` files |
| | `svelte` | Rich Harris | `svelte`/`@sveltejs/kit`, `.svelte` |
| | `solid` | Ryan Carniato | `solid-js`/`@solidjs/start` |
| HTTP/Web | `http-api` | Fielding, Nottingham, Sturgeon | Route handlers, OpenAPI specs |
| | `hypermedia` | Gross, Nottingham | HTMX detected |
| | `ui` | Keith, Pickering, Wathan, Frost | HTML/CSS/JSX |
| | `uswds` | Frost | `@uswds/uswds`, `usa-*` classes |
| Security | `identity` | Parecki, Richer | OAuth/OIDC/JWT/session libs |
| | `cryptography` | Valsorda, Green | Crypto/password-hash/TLS code |
| Data | `database` | Kleppmann, Winand | Migrations, ORM, raw SQL |
| | `data-engineering` | Beauchemin, Handy, Sculley | Airflow/dbt/Spark/ML pipelines |
| AI | `ai-llm` | Willison, Husain, Yan | LLM clients, RAG, embeddings, evals |
| Operations | `cicd` | Humble & Farley, Rice | CI workflows, Dockerfile, lockfiles |
| | `infrastructure` | Morris, Hightower | Terraform, K8s, Helm |
| | `observability` | Majors, Sridharan | Telemetry, logging, traces |
| | `performance` | Gregg, Thompson | Hot-path code, benchmarks |
| | `testing` | Dodds, Feathers | Test suites and runner configs |
| | `distributed` | Newman, Richardson | Queues, RPC, webhooks, sagas |
| Fallback | `secondary` | Ramalho, Soueidan | Loaded on demand on impasse |

Trigger conditions are canonical and machine-parseable in `context/panels/triggers.md`, evaluated deterministically by `panel_detect.py` (which also parses manifest files directly — `package.json`, `pyproject.toml`, `go.mod`, etc. — to detect framework dependencies, not just file extensions). Hazard tables and synthesis rules live in each panel's own file. When more than five panels activate on one review, findings are prioritized by severity across all panels rather than enumerated panel-by-panel.

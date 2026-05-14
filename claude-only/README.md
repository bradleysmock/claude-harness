# claude-harness

A Claude Code configuration harness for a structured, two-checkpoint SDLC pipeline: slash commands, expert review panels, and a working agreement that keeps Claude autonomous between human decisions.

## What's included

- **Working agreement** (`CLAUDE.md`): roles, workflow, artifact constraints, TDD rules, communication norms, and universal **Code Generation Rules** (language-neutral principles)
- **10 slash commands**: the full pipeline from problem statement to merged branch, plus `/gate` and `/score-spec`
- **6 expert review panels** (`.claude/panels/`): loaded dynamically based on file scope — Core, Python, HTTP/API, UI, AI/LLM, Secondary
- **Polyglot code generation rules** (`.claude/rules/`): universal principles plus per-language addenda for Python, JavaScript, TypeScript, Go, Rust
- **Critic subagent** (`.claude/agents/critic.md`): read-only reviewer with restricted tools; shared brief in `.claude/critic-brief.md`
- **Polyglot validation hooks** (`.claude/hooks/`): PreToolUse pattern guard (dispatches by extension), PostToolUse linter/SAST gate, Stop full-suite gate (dispatches by detected stack)
- **Settings** (`.claude/settings.json`): permission allowlist for safe ops across Python/JS/TS/Go/Rust toolchains and hook wiring

## Setup

Copy the `.claude/` directory and `CLAUDE.md` into your project root.

```bash
cp -r .claude /path/to/your/project/
cp CLAUDE.md /path/to/your/project/
```

Commit both to your repository. The `.claude/state/` directory is runtime-only and gitignored.

## Workflow

Work runs autonomously between two human checkpoints.

```
/problem  →  [autonomous: problem → requirements → solution → critic loop]
                                                                    ↓
                                                       CHECKPOINT 1: approve to implement
                                                                    ↓ approved
/implement  →  [autonomous: worktree → TDD → critic/review loop]
                                                          ↓
                                             CHECKPOINT 2: approve to merge
                                                          ↓ approved
/merge
```

## Slash commands

| Command | Purpose |
|---------|---------|
| `/problem` | Entry point: clarity check → problem → requirements → solution → critic loop → spec-score → Checkpoint 1 |
| `/implement` | TDD implementation in a worktree → `/gate` → critic/review loop (max 2 rounds) → Checkpoint 2 |
| `/merge` | Merge approved branch into main, remove worktree, append must-fix items to `_learnings.md`, rebase in-flight branches |
| `/gate` | Manual gate runner: ruff + mypy + bandit + pytest; writes `.tickets/XXXX/gate-findings.md` |
| `/score-spec` | Validates requirements.md and solution.md are specific enough to implement |
| `/requirements` | Manual requirements pass (escape hatch if `/problem` was not used) |
| `/solution` | Manual solution pass with lead discussion before writing |
| `/refine` | Iterate on an existing solution before implementation |
| `/review` | Manual code review — reports findings directly without a critic loop |
| `/critique` | Expert panel code review — loads panels based on file scope, produces a structured report |

## Polyglot rules & gates

The harness is language-agnostic at its core. Generation-time rules and post-write gates dispatch on file extension; the Stop hook detects stacks from project-root markers and runs the appropriate gate set per stack. A worktree may have multiple stacks; each is run independently.

| Stack       | Marker(s)                              | Pre-write rules               | Post-write gate         | Stop-gate full suite                       |
|-------------|----------------------------------------|-------------------------------|-------------------------|--------------------------------------------|
| Python      | `pyproject.toml` / `*.py`              | `.claude/rules/python.md`     | ruff + bandit           | ruff + bandit + mypy + pytest              |
| JavaScript  | `package.json`                          | `.claude/rules/javascript.md` | eslint                  | eslint + `npm test`                        |
| TypeScript  | `tsconfig.json` / `*.ts`               | both above                    | eslint                  | eslint + tsc + `npm test`                  |
| Go          | `go.mod`                                | `.claude/rules/go.md`         | gofmt                   | gofmt + `go vet` + `go test`               |
| Rust        | `Cargo.toml`                            | `.claude/rules/rust.md`       | rustfmt                 | `cargo fmt --check` + clippy + `cargo test`|

All stacks also enforce universal rules (`.claude/rules/universal.md`): hardcoded secrets, SQL interpolation, unsafe redirects, internal-error echo. Missing tools are skipped — the harness degrades gracefully.

## Expert panels

Panels are loaded on demand by `/critique` and by the critic agents in `/problem` and `/implement`. Only the panels relevant to the files in scope are read.

| Panel | Loaded when | Experts |
|-------|-------------|---------|
| Core | Always | Martin, Ousterhout, Fowler, Beck, McGraw, Evans |
| Python | `*.py` files in scope | Hettinger, Beazley |
| HTTP/API | Route handlers in scope | Gross, Nottingham |
| UI | Templates or static assets in scope | Keith, Pickering, Wathan, Frost |
| AI/LLM | LLM client code in scope | Willison |
| Secondary | On demand (primary panel impasse only) | Ramalho, Soueidan |

## Ticket tracking

All work is tracked under `.tickets/`. Ticket numbers are assigned atomically via a lock file and a `NEXT_TICKET` counter.

```
.tickets/
  NEXT_TICKET            # next available number
  XXXX-<slug>/
    problem.md           # 40-line hard limit
    requirements.md      # 60-line hard limit
    solution.md          # 80-line hard limit
    status.md            # current stage + metadata
```

## Worktrees

Implementation happens in a git worktree at `.worktrees/XXXX-<slug>` on branch `ticket/XXXX-<slug>`. The `.worktrees/` directory is gitignored globally and never committed.

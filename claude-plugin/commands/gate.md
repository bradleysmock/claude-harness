Manual gate runner — detects the stack(s) present in a ticket's worktree and runs the corresponding lint/SAST/test gates. Writes structured findings to `.tickets/XXXX-<slug>/gate-findings.md`.

## Ticket resolution

A ticket number argument is required. If none is provided, scan `.tickets/` for tickets with `status: implementing` or `status: review-ready`. If exactly one exists, use it. Otherwise list candidates and stop.

## Stack detection

Inspect the worktree root for these markers and run gates for every stack that matches. A worktree may have multiple stacks.

| Marker(s) present                                  | Stack       |
|----------------------------------------------------|-------------|
| `pyproject.toml`, `setup.py`, `setup.cfg`, `*.py` | Python      |
| `package.json` + `tsconfig.json` (or `*.ts`)       | TypeScript  |
| `package.json` (without TS markers)                | JavaScript  |
| `go.mod`                                            | Go          |
| `Cargo.toml`                                        | Rust        |

## Gates per stack

For each detected stack, run the gate set below. Skip any individual gate whose tool is absent and note "not installed" in findings. Each stack's tools are checked against the **changed files** (`git diff --name-only main`) for per-file gates and the **full worktree** for test/build gates.

### Python
| Gate    | Command (per file or per project)                     |
|---------|--------------------------------------------------------|
| ruff    | `ruff check --output-format=concise <files>`          |
| mypy    | `mypy --no-error-summary <files>`                     |
| bandit  | `bandit -ll -q -f txt <files>`                        |
| pytest  | `pytest -q --no-header`                               |

### JavaScript / TypeScript
| Gate    | Command                                                |
|---------|--------------------------------------------------------|
| eslint  | `npx --no-install eslint --no-color .`                 |
| tsc     | `npx --no-install tsc --noEmit` (TS only)             |
| tests   | `npm test --silent`                                    |

### Go
| Gate    | Command                                                |
|---------|--------------------------------------------------------|
| gofmt   | `gofmt -l .` (any output ⇒ unformatted)                |
| vet     | `go vet ./...`                                         |
| tests   | `go test ./...`                                        |

### Rust
| Gate    | Command                                                |
|---------|--------------------------------------------------------|
| fmt     | `cargo fmt --check`                                    |
| clippy  | `cargo clippy -- -D warnings`                          |
| tests   | `cargo test --quiet`                                   |

## Output

Write `.tickets/XXXX-<slug>/gate-findings.md`:

```markdown
# Gate Findings — XXXX-<slug>

**Run at**: YYYY-MM-DD HH:MM
**Worktree**: .worktrees/XXXX-<slug>
**Stacks detected**: <comma-separated, e.g. "python, typescript">

## <stack>

### <gate>
<concise output or "clean">
```

Then print a one-line summary: `gate: <stack>=<PASS|FAIL: gates-failing>` for each stack.

## Failure handling

This command **does not fix findings** — it only records them. The caller (`/implement` or the lead) decides what to do.

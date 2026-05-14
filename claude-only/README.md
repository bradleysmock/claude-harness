# claude-harness

A Claude Code configuration harness for a structured, two-checkpoint SDLC pipeline: slash commands, expert review panels, and a working agreement that keeps Claude autonomous between human decisions.

## What's included

- **Working agreement** (`CLAUDE.md`): roles, workflow, artifact constraints, TDD rules, and communication norms
- **8 slash commands**: the full pipeline from problem statement to merged branch
- **6 expert review panels**: loaded dynamically based on file scope — Core, Python, HTTP/API, UI, AI/LLM, Secondary

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
| `/problem` | Entry point: clarity check → problem → requirements → solution → critic loop → Checkpoint 1 |
| `/implement` | TDD implementation in a worktree, critic/review loop, Checkpoint 2 |
| `/merge` | Merge approved branch into main, remove worktree, rebase in-flight branches |
| `/requirements` | Manual requirements pass (escape hatch if `/problem` was not used) |
| `/solution` | Manual solution pass with lead discussion before writing |
| `/refine` | Iterate on an existing solution before implementation |
| `/review` | Manual code review — reports findings directly without a critic loop |
| `/critique` | Expert panel code review — loads panels based on file scope, produces a structured report |

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

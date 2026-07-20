# Solution

**Ticket**: 0069
**Title**: Ticket CLI deliver subcommand

## Approach

Add a `deliver` case to `ticket.py`'s `_main()` dispatch, reusing the
existing ledger-based resolution mechanism (`_resolve_claim` +
`_read_ticket_docs`) that `cancel`/`abandon`/`reopen` already rely on —
**not** a new filesystem-only resolver — then enforcing `review-ready` and
calling the already-implemented `deliver_squash()`. No change to
`deliver_squash`, `deliver-batch`, or any flow doc.

## Components

| Component | Responsibility |
|-----------|-----------------|
| `deliver` CLI case | New branch in `_main()`, alongside `deliver-batch`. `record = _resolve_claim(repo, ident)` → `full_slug`, `branch`, `title`. `docs = _read_ticket_docs(repo, full_slug, branch)` (worktree-or-branch-ref, same pattern `cancel`/`reopen` use). If `"status.md" not in docs`, raise `FileNotFoundError` explicitly (never index-and-KeyError). Parse `status:` from it; if not `review-ready`, print the actual status and return 1. Otherwise call `deliver_squash(repo, branch, full_slug, title)`, print the returned subject, return 0. |
| Error handling | One `try/except (FileNotFoundError, RuntimeError)` wraps resolution through delivery — `FileNotFoundError` (no such claim, or no `status.md`), `RuntimeError` (every git-command failure inside `deliver_squash`, including a `merge --squash` conflict — `git()` always raises `RuntimeError` itself, never lets `subprocess.CalledProcessError` escape) — both print to stderr and return 1, never a traceback. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `_resolve_claim` + `_read_ticket_docs` over a new resolver | These already implement the repo's one documented "worktree-first, branch-ref fallback" resolution rule (`context/harness-reference.md` "Ticket resolution") and are what `cancel`/`abandon`/`reopen` use for the identical in-flight-ticket case. A filesystem-only `.worktrees/`-glob resolver (rejected design) has no branch-ref fallback and duplicates a solved problem. |
| No `--push` flag | `deliver_squash` always publishes; a flag that does nothing would mislead. Matches `deliver-batch`'s existing shape. |
| Reuse `deliver_squash` unmodified | Already implements the full contract (squash, archive, push, ledger event, cleanup) and is unit-tested; the CLI layer is a thin, testable wrapper. |
| `except (FileNotFoundError, RuntimeError)` only | `git()` always runs `subprocess.run(..., check=False)` and raises `RuntimeError` itself after inspecting the return code — `subprocess.CalledProcessError` never occurs in this codebase, so catching it would be dead code. |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | `deliver` case reachable in `_main()`; no `--push` consumed/required. |
| FR-2        | Unit        | Resolves by bare number/4-digit id/full slug via `_resolve_claim`; `docs` missing `status.md` → explicit `FileNotFoundError`, not `KeyError`. |
| FR-3        | Unit        | `deliver_squash` called with `(repo, branch, full_slug, title)` from the resolved record; returned subject printed. |
| FR-4        | Unit        | Fixture `status.md` at `implementing` → exit 1, `deliver_squash` never called. |
| FR-5        | Unit        | `deliver_squash` monkeypatched to raise `RuntimeError` (rejected-push and squash-conflict shape) → exit 1, message on stderr, no traceback. |
| FR-6        | Unit        | `ticket.py deliver` (no args) → usage message, exit 2. `ticket.py deliver bogus-id` → `_resolve_claim`'s `FileNotFoundError` caught, exit 1, no traceback. |
| Integration | Integration | Fixture repo: claim → hand-set `review-ready` → `ticket.py deliver <id>` → assert squash commit, `.tickets/completed/<slug>/status.md` == `done`, ledger `delivered` event. |

## Tradeoffs

- **Reuse `_resolve_claim`/`_read_ticket_docs` over a new resolver because**: they are the already-correct, already-tested mechanism for this exact case; a narrower alternative would silently regress the branch-ref (no local worktree) case.
- **Thin CLI wrapper over reimplementing delivery logic because**: `deliver_squash` is the single source of truth for the squash/archive/push/ledger sequence; duplicating it in the CLI layer would let the two drift.

## Risks

- `deliver-batch`'s existing CLI case has no equivalent `try/except` around
  `deliver_squash_batch` — a batch delivery failure still tracebacks today.
  Out of scope here (`deliver-batch`'s behavior is unchanged), but the two
  sibling commands will diverge in error-reporting strictness; worth a
  follow-up ticket rather than silent drift.
- The pre-existing worktree-path-nesting bug found while claiming this
  ticket (`_create_branch_and_worktree` writes the claim stub under
  `worktree/.tickets/` instead of the project's actual nested subdirectory)
  is unrelated to this design (the ledger-based resolver never constructs
  that path) and untouched here.

## Implementation Order

1. Write unit tests for the `deliver` CLI case (red): happy path, wrong
   status, missing ident, unresolvable ident, `RuntimeError`.
2. Wire the `deliver` case into `_main()` using `_resolve_claim` +
   `_read_ticket_docs` + the combined exception handler.
3. Green the unit tests; add the fixture-repo integration test.
4. Gate-exact ruff + mypy on `ticket.py`; full targeted pytest.

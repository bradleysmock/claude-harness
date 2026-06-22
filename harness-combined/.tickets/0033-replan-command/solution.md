# Solution

**Ticket**: 0015
**Title**: Replan command

## Approach

Add a `/replan XXXX` command as a new Markdown command spec (`commands/replan.md`) following the harness command pattern. The command re-derives `solution.md` from the current `problem.md` and `requirements.md`, runs the critic loop (up to 2 rounds, explicitly capped in the command spec itself), presents a unified diff, updates `status.md` to `solution`, and commits. It operates entirely on `main` (no worktree); if a worktree exists, it presents a Checkpoint-style confirmation prompt and waits for lead approval before proceeding.

## Components

| Component | Responsibility | Key Interfaces |
|-----------|---------------|----------------|
| `commands/replan.md` | Full command spec — ticket resolution, status guard, snapshot, regeneration, critic loop, diff, commit | Follows existing command spec pattern |
| Snapshot step | Capture current `solution.md` via `git show HEAD:<path>` into a shell variable (no filesystem write) before regeneration; eliminates partial-write risk | `git show HEAD:.tickets/XXXX-slug/solution.md` |
| Diff presentation | Produce unified diff of snapshot string vs new `solution.md`; handle `git diff --no-index` exit-code 1 explicitly | `diff_output=$(git diff --no-index <(echo "$snapshot") solution.md \|\| true)` |
| Worktree guard | Detect active worktree via `git worktree list`; present Checkpoint-style prompt (not stdin `read`) for confirmation | `git worktree list \| grep ticket/XXXX-slug` |
| Critic loop | Same subagent spawn as `/problem` Phase 5; explicitly cap at 2 rounds in `replan.md` (not delegated by reference) | `subagent_type: critic`, rounds 1–2 |
| Regeneration observability | Log rendered prompt, full model response, and tool calls for the solution-regeneration LLM invocation; per CLAUDE.md hard constraint | Trace logged before `solution.md` write |

## Trust Boundary

Ticket artifact files (`problem.md`, `requirements.md`) are **lead-authored content** in the current workflow — the trust boundary is: lead → git commit → harness command reads committed file. However, the regeneration step reads these files into an LLM context that also has write-capable tools (overwriting `solution.md` and committing to `main`). The structural control is **agent-turn scoping**: the read pass (ingesting `problem.md` / `requirements.md` into context) and the write pass (producing `solution.md`) occur as separate, sequenced steps within the command — the model does not hold write tool access while consuming the artifact text. This separation is an architectural constraint, not a social one. Additionally, this command is a single-lead workflow: only the lead can author committed ticket artifacts. If future integrations source content from external issue trackers or multi-contributor PRs, a sanitization step must be added at the ingestion boundary before the read pass — this is a documented future gate, not deferred until implementation.

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| New `commands/replan.md` file | Consistent with how all other commands are implemented; self-contained, no code changes to existing commands |
| `git show HEAD:<path>` for snapshot | In-memory capture; eliminates temp-file injection risk and partial-write race; no cleanup needed |
| `git diff --no-index` with explicit `\|\| true` | Captures diff output separately from exit code; exit 1 (files differ) is the normal case, not an error |
| Checkpoint-style prompt for worktree confirmation | Matches harness interaction pattern; compatible with agent-driven execution (no bare `read`) |
| Explicitly state 2-round critic cap in `replan.md` | Avoids silent inheritance if `/problem` Phase 5 changes; makes the behavior self-contained |
| Commit message encodes prior status on rollback | Distinguishes refresh (`solution ← solution`) from rollback (`solution ← implementing`) in git log |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | Ticket resolution finds correct directory; ambiguous input shows list |
| FR-2        | Unit        | Status guard rejects `problem`, `requirements`, `done`, `cancelled`; accepts `solution`, `implementing`, `review-ready`, `changes-requested` |
| FR-3        | Integration | `problem.md` and `requirements.md` are read before regeneration |
| FR-4        | Integration | Snapshot captured via `git show`; diff reflects pre-replan content |
| FR-5        | Integration | Regenerated `solution.md` contains all required sections |
| FR-6        | Integration | Critic spawned; at least 1 round; second round triggered if BLOCKER found in round 1 |
| FR-7        | Integration | Diff printed after command; fixture with identical old/new content shows "no changes" notice |
| FR-8        | Integration | `status.md` shows `status: solution` and today's date after run |
| FR-9 (normal)  | Integration | Single commit with message `chore(ticket): XXXX replan (status: solution)` when prior status was `solution` |
| FR-9 (rollback)| Integration | Fixture ticket at `status: implementing`; commit message uses rollback form encoding prior status |
| FR-10          | Integration | Worktree present → Checkpoint prompt shown → aborts on `no` → proceeds on `yes` |
| NFR-1          | Integration | Fixture-based: run twice on same `requirements.md`; both outputs pass section-presence check |
| NFR-2          | Unit        | Command succeeds when ticket has no prior `solution.md` (`git show` returns empty); diff section shows empty |
| FR-7 (no-change path) | Integration | Fixture with mocked identical old/new `solution.md`; verifies "no changes" notice |
| LLM observability | Integration | Trace/log entry produced for the regeneration LLM invocation before `solution.md` write |

## Tradeoffs

- **Chose `git show HEAD:<path>` snapshot over filesystem backup**: Eliminates the entire class of temp-file path-traversal and partial-write risks identified in D-01/D-03. Tradeoff: if `solution.md` has uncommitted local edits, `git show HEAD` captures the last committed version, not the local version. This is acceptable — the harness requires all ticket artifacts to be committed on `main` after every transition; uncommitted artifacts represent an erroneous state.
- **Chose Checkpoint-style prompt over stdin `read`**: Consistent with agent-driven execution model; bash `read` is not available in the harness's interaction context. Tradeoff: slightly heavier than a raw `y/n` prompt.
- **Chose status rollback to `solution` unconditionally with named commit**: Rolling back from `implementing` or `review-ready` is a named domain event in the git log. Tradeoff: requires the lead to reconcile the worktree manually after replanning.
- **Accepting risk of**: LLM non-determinism means two runs on identical inputs produce different `solution.md` content; the diff will show changes even if requirements didn't change. NFR-1 is verified structurally (section presence), not content-equivalently.

## Risks

- **Worktree/spec staleness with status inversion**: If a ticket is `implementing` and `/replan` rolls status back to `solution`, the existing worktree branch still exists. The worktree's gate pipeline or `/build` completion path could subsequently write a `review-ready` transition over the `solution` status that `/replan` just committed — creating a status inversion in git history. Mitigation: command output must explicitly name the worktree path, warn that the worktree must be removed or reconciled before resuming, and note that running `/build` on the old worktree after replanning is unsafe. Suggest `git worktree remove .worktrees/XXXX-slug` and re-running `/build XXXX` from scratch.
- **Commit on main while worktree is ahead**: Safe (different branches) but the lead must rebase or merge before the next `/build`. The command output must name this requirement explicitly, not just note it generally.
- **`git show HEAD` fails for a new ticket with no prior commit**: If `solution.md` was never committed, `git show HEAD:.tickets/...` returns an error. The command must handle this with an empty snapshot (NFR-2 path).
- **LLM regeneration failure produces empty or malformed solution**: If the regeneration call fails (network error, context overflow, model error) or returns an empty/malformed response, the command must abort before overwriting `solution.md`. The write is conditional on receiving a non-empty, structurally-valid regenerated solution. This is a fail-closed requirement — partial writes are never committed.

## Implementation Order

1. Write `commands/replan.md` — ticket resolution and status guard (FR-1, FR-2).
2. Add worktree detection and Checkpoint-style confirmation section (FR-10).
3. Add snapshot section using `git show HEAD:<path>` with empty-snapshot fallback (FR-4, NFR-2).
4. Add solution regeneration section mirroring `/problem` Phase 4 (FR-3, FR-5).
5. Add critic loop section with explicit 2-round cap (FR-6).
6. Add diff presentation section with `|| true` exit-code handling and "no changes" notice (FR-7, D-07 path).
7. Add status update and commit section with rollback-aware commit message (FR-8, FR-9).
8. Add unit tests for ticket resolution, status guard, and empty-snapshot path.
9. Add integration tests for happy path, worktree-present guard, rollback scenario, and NFR-1 structural check.

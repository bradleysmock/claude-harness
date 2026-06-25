# Requirements

**Ticket**: 0003
**Title**: Squash-merge ticket delivery: two commits to main per ticket

## Functional Requirements

1. `/deliver` must merge the feature branch with a **squash merge** (`git merge --squash`), producing exactly one "completed work" commit on `main` that contains the entire branch diff — no per-worktree-commit history and no `--no-ff` merge commit.
2. The terminal status transition (`→ done`) and the archive move into `.tickets/completed/<slug>/` must be folded into that **same** squashed commit, so a normally-delivered ticket adds exactly one commit at delivery.
3. Ticket branch and worktree must be created at **claim time** (`/problem` Phase 1), not at `/build` time, so design artifacts have a branch to live on — but **only after the claim push wins**, so a renumber-on-reject leaves no orphaned branch/worktree.
4. The `claim` commit must remain the only `main` commit written before delivery, and its `status.md` stub must carry a brief work description, the `owner`, and the `branch` name. Number claiming must stay atomic (first-push-wins, loser renumbers). Post-claim, `main` must never re-touch a claimed ticket's `.tickets/<slug>/` directory until delivery, so the delivery squash resolves that path cleanly (merge base = claim stub; only the branch changed it).
5. After claim, every status transition and every artifact write (`problem.md`, `requirements.md`, `solution.md`, spec/task files, implementation) must be committed to the **feature branch and pushed to origin** — never committed to `main`. The states `solution`, `implementing`, `review-ready`, `changes-requested` are all branch-only.
6. `/reopen` must fork a **fresh** branch `ticket/XXXX-<slug>` from `main` HEAD (the prior delivery squashed and deleted the original branch, so its per-commit history is gone — the squashed commit is the new base) and restore the ticket dir from `completed/` **onto that branch**, setting `solution`. The next `/deliver` squashes the reopened work into a further commit on `main` (additional work in subsequent commits).
7. `/cancel` and `/abandon` must reconcile with branch-at-claim: they must remove the worktree+branch that now exist from claim time, and a never-delivered ticket must leave only its `claim` commit on `main` plus a terminal archive commit.
8. The `ticket_commit_guard` Stop hook must also block on uncommitted ticket metadata inside any **active worktree**, discovered per-ticket from `.worktrees/<slug>/`, not only `main`'s `.tickets/` — and must behave correctly whether the turn's cwd is the main root or inside a worktree.
9. Status-reading skills (`/status`, `/ticket-status`, `/suggest`) must read a ticket's worktree `status.md` when its `.worktrees/<slug>/` exists locally (so the local lead sees real progress), falling back to `main`'s claim stub otherwise. The cross-machine limitation (a developer without the worktree sees `claimed`) is accepted and must be stated in the skill text.

## Non-Functional Requirements

1. Stdlib-only Python; `subprocess` always called with argument lists (no shell concatenation).
2. Scoped `git add` only — never `git add -A` for ticket metadata.
3. No behavioral change to the gate engine, spec generation, or critic loop.

## Test Strategy

| Type | Rationale |
|------|-----------|
| Unit (content-assertion) | Flows/reference assert squash merge, branch-at-claim, branch-only states, folded done+archive, claim-stub fields, push-throughout. Mirrors `tests/test_ticket_archiving.py`. |
| Unit (ticket.py) | `claim` creates branch (+worktree) and pushes the stub; `set_status` commits to and pushes the branch; renumber-on-push-reject still holds. |
| Unit (hook) | `ticket_commit_guard` flags uncommitted metadata in an active worktree. |

## Acceptance Criteria

- A simulated deliver leaves exactly two commits on `main` (claim + squashed work); the squashed commit's tree contains both the full code diff and `completed/<slug>/status.md` with `status: done`.
- `ticket.py claim` writes+pushes the stub (description+owner+branch) and, **only after the push wins**, creates `ticket/XXXX-<slug>` and its worktree; a simulated push-reject renumber leaves **no** orphaned branch or worktree.
- No flow commits `solution`/`implementing`/`review-ready` to `main`; all are branch commits that are pushed.
- `/reopen` recreates the branch+worktree and a following `/deliver` adds one further squashed commit.
- All content-assertion and unit tests pass.

## Open Questions

(none — design direction approved by the lead: claim commit is the only pre-delivery `main` commit; artifacts live on the pushed branch.)

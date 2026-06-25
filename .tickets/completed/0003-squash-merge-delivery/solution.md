# Solution

**Ticket**: 0003
**Title**: Squash-merge ticket delivery: two commits to main per ticket

## Approach

Move the state split's boundary: `main` keeps only the **claim** commit and the **squashed delivery** commit; everything between lives on the feature branch, pushed to origin. The branch + worktree are created at **claim time** (`/problem` Phase 1) so the design phase has a branch to write to. `/deliver` switches from `git merge --no-ff` to `git merge --squash`, then folds `→ done` + the `completed/` archive into that single commit.

**Three load-bearing invariants** (resolve the squash-conflict and orphan-branch risks):
- **All post-claim states are branch-only.** `main` carries **only** `claimed` + the terminals (`done`/`cancelled`/`abandoned`). `solution`, `implementing`, `review-ready`, `changes-requested` are **all** committed+pushed to the branch — including `implementing`, which `/build` Step 2 previously pushed to `main`. So `main` genuinely never re-touches a claimed ticket's `.tickets/<slug>/` until that ticket's own delivery. (`/deliver` Step 9's rebase-downgrade of *other* in-flight tickets likewise commits to **their** branches, not `main`.)
- **Branch-authoritative dir → clean squash.** Given the above, at delivery the squash's merge base for `.tickets/<slug>/status.md` = the claim stub (main's last touch), and only the branch changed it → clean resolution, no conflict (this replaces the old `--no-ff` clean-merge note, whose "build forks after pushing implementing to main" causal chain no longer holds).
- **Create-after-push:** `claim()` creates the branch+worktree **only after** the winning push, outside the renumber loop, so a push-reject renumber leaves no orphan.

## Components

| Component | Change |
|-----------|--------|
| `ticket.py` `claim()` | Loop = stub write + commit + push (renumber on reject) **unchanged**; after the loop wins, create branch `ticket/XXXX-<slug>` + worktree `.worktrees/XXXX-<slug>`. Stub carries title/owner/branch (FR-4). |
| `ticket.py` `set_status()` | Accept the worktree as `repo`; commit the transition to the branch and `git push` it (FR-5). |
| `ticket.py` `deliver_squash()` (new) | Encapsulate the exact sequence (below); unit-testable (FR-1/2). |
| `commands/problem.md` | Phase 1 creates branch+worktree post-claim; Phases 2–4 write artifacts **in the worktree**, commit+push to the branch. **Delete** the Phase 5 "commit design to main / `git push`" block — it becomes a branch commit (FR-3/5). |
| `context/flows/build-ticket.md` | Worktree pre-exists from claim — **remove** Step 2 creation; resume it. The `implementing` transition (and `review-ready`) commit+push to the **branch** via `set_status(repo=worktree)`, **not** `main` (FR-5). |
| `context/flows/deliver-ticket.md` | Call `deliver_squash()`; drop the two-commit 6a/6b split and the `--no-ff` status-merge note. **Step 9**: other tickets' rebase-downgrade `→ implementing` commits to their branches, not `main` (FR-1/2). |
| `commands/reopen.md` | The prior delivery squashed + **deleted** the branch, so reopen forks a **fresh** `ticket/XXXX-<slug>` from `main` HEAD, restores the dir from `completed/` **onto that branch** (not main), sets `solution`; the squashed commit is its base. Rewrite Steps 4–6; fix the stale note at reopen.md:50-53 (FR-6). |
| `commands/cancel.md`, `abandon.md` | Remove the now-claim-time worktree+branch; leave claim + terminal archive only. Route the terminal transition through `ticket.py set-status` (cancel.md currently hand-commits) (FR-7). |
| `hooks/ticket_commit_guard.py` | Resolve the main root via `git rev-parse --git-common-dir` (→ parent) so it works when cwd is a worktree; scan `.tickets/` once **per existing checkout root** (main + each `.worktrees/*`); never flag a ticket dir that is simply absent on `main` (FR-8). |
| `skills/status`, `commands/ticket-status.md`, `skills/suggest` | Per-ticket: read `.worktrees/<slug>/status.md` when that worktree exists, else `main` stub; state the cross-machine `claimed` limitation (FR-9). |
| `context/harness-reference.md` | Rewrite State split + Committing-metadata + Worktrees; transitions table: `main` shows **only** `claimed` + terminals, all other states **branch-only**; delete the "build forks after pushing implementing to main" causal paragraph. |
| `tests/` | Content-assertion + `ticket.py` git-sim + hook unit (TDD — written with each step). |

## deliver_squash() sequence (single commit)

Mirrors the existing archive pattern (OS `mv` + `git rm --cached` + `git add`) — **not** `git mv`, which is unsound against the index `merge --squash` leaves:

1. `git -C <main> merge --squash <branch>` — stages branch diff (code + branch's `.tickets/<slug>/`), no commit.
2. OS `mkdir -p .tickets/completed`; OS `mv .tickets/<slug> .tickets/completed/<slug>`.
3. Rewrite `.tickets/completed/<slug>/status.md` → `status: done` (at the **new** path, so the staged blob is the `done` content).
4. `git rm -r --cached .tickets/<slug>/` (clears the just-squash-staged old path); `git add -- .tickets/completed/<slug>/` (code changes are already squash-staged).
5. `git commit -m "feat: XXXX <title> (squash)"` — **one** commit: full code diff + `completed/<slug>/` at `done`, and **no** `.tickets/<slug>/` entry.
6. `git push`. Then remove worktree + delete branch.

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `git merge --squash` | Stages without committing → done+archive fold into one commit (FR-2). |
| Worktree-at-claim | Worktrees already core to the harness; cleanest way to put `/problem` output on a branch. |
| Claim commit stays on `main`+push | Number reservation must stay atomic (FR-4); only load-bearing `main` signal pre-delivery. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit (git-sim) | After `deliver_squash` on a sim repo: commits on `main` since claim == 1; no merge commit. |
| FR-2 | Unit (git-sim) | HEAD tree contains `completed/<slug>/status.md` (`done`) + the code diff, and **no** `.tickets/<slug>/` entry, in one commit. |
| FR-3 | Unit (ticket.py) | `claim` creates branch + worktree (post-push). |
| FR-4 | Unit (ticket.py) | Stub fields present; simulated push-reject renumbers AND leaves no branch/worktree for the dropped number. |
| FR-5 | Unit (content) | problem/build flows commit+push transitions & artifacts (incl. `implementing`) to the branch; no `implementing→main`; no main design commit. |
| FR-6 | Unit (content + git-sim) | reopen forks a fresh branch from `main` HEAD, restores from `completed/` onto it; second deliver adds one more squashed commit. |
| FR-7 | Unit (content) | cancel/abandon remove worktree+branch (route via `set-status`); leave claim + terminal archive only. |
| FR-8 | Unit (hook) | guard flags uncommitted metadata in a `.worktrees/<slug>/.tickets/`; correct when cwd **is** the worktree and the ticket dir is absent on `main`. |
| FR-9 | Unit (content) | three skills read `.worktrees/<slug>/status.md` when present; limitation noted. |

## Tradeoffs

- **Branch-at-claim over design-on-`main`**: yields the two-commit history; cost is `main` showing only `claimed` for in-flight tickets (progress is on the pushed branch + local worktree). Accepted.
- **Squash erases per-commit authorship**: under multi-dev renumber, owner (claim) and committer (deliverer) can differ — `main` attributes the squashed commit to the deliverer; `owner` survives in the archived `status.md`. Noted.

## Risks

- **Worktree lifecycle now spans `/problem`→`/deliver`** → build/deliver/reopen resume tests.
- **reopen.md stale note** (branch deleted, build recreates) directly contradicts FR-6 → reopen.md is in the change set with that exact fix.
- **Bootstrapping**: 0003 is delivered under the current `--no-ff` flow; the new flow applies to tickets claimed after it merges. FR-1/2 tests run against a **simulated** repo, not 0003's own delivery.

## Implementation Order

1. `ticket.py` — `claim` (create-after-push), `set_status` (branch+push), `deliver_squash`. *(+unit tests, TDD)*
2. `harness-reference.md` — rewrite State split / metadata / worktrees / transitions table (the contract).
3. `commands/problem.md` — branch-at-claim; artifacts on branch; delete Phase 5 main commit. *(+content tests)*
4. `context/flows/build-ticket.md` — resume pre-existing worktree; pushed branch-only transitions. *(+content tests)*
5. `context/flows/deliver-ticket.md` — call `deliver_squash`. *(+content + git-sim tests)*
6. `commands/reopen.md`, `cancel.md`, `abandon.md` — recreate/remove worktree+branch. *(+content tests)*
7. `hooks/ticket_commit_guard.py` — worktree discovery. *(+hook unit test)*
8. `skills/status`, `commands/ticket-status.md`, `skills/suggest` — worktree-aware reads. *(+content tests)*

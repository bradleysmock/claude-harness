# Problem Statement

**Ticket**: 0003
**Title**: Squash-merge ticket delivery: two commits to main per ticket
**Date**: 2026-06-24

## Problem

`/deliver` merges a ticket's feature branch with `git merge --no-ff`, dragging every worktree commit (`feat`, each repair-round `fix`, `test`) onto `main`. On top of that, the state-split commits coarse status transitions (`solution`, `implementing`, `done`, archive) directly to `main`. A single finished ticket therefore litters `main` with ~6–8 commits, most of them intra-branch churn and one-line chores, making the history hard to read.

## Impact

- Anyone reading `main`'s history cannot tell ticket boundaries from noise.
- `git log`, `git blame`, and bisect are muddied by repair-round and metadata commits that have no standalone meaning.
- Affects every ticket delivered through the harness.

## Success Criteria

- A delivered ticket leaves exactly **two** commits on `main`: a `claim` commit (work starting) and one squashed "completed work" commit.
- The `claim` commit carries a brief work description, the owner, and the branch name.
- All status transitions and design/implementation artifacts are committed to the **feature branch and pushed to origin** throughout, never to `main` before delivery.
- A reopened ticket forks a fresh branch from `main` and adds further squashed commit(s) on re-delivery (its in-progress history lives on that branch until the next squash).
- Multi-developer number-claim atomicity (first-push-wins) is preserved.

## Out of Scope

- Changing the gate/repair engine, spec generation, or critic loop.
- Squashing or rewriting commits already on `main`.
- Building a network/GitHub-Issues path (the `source`/`external_id` seam stays reserved).

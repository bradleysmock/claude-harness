---
name: rollback
description: Roll back a delivered ticket by reverting its merge commit with a standardized `git revert`. TRIGGER when the user asks to "roll back ticket XXXX", "revert the delivery of XXXX", "undo a delivered ticket", or invokes /rollback (optionally with `--dry-run` to preview). SKIP when the ticket has not been delivered (`status` is not `done` — nothing to revert), when the user wants to cancel in-flight work before merge (use /cancel), or when they want to re-open a completed ticket for further work (use /reopen).
---

# Rollback skill — `/rollback`

Take a **delivered** ticket number and produce a clean, standardized `git revert` of that ticket's
merge commit. Rollback uses `git revert` — a new forward commit that inverts the merge — **not**
`git reset`: history is preserved and the rollback is itself reversible.

The procedure **fails closed**: it validates input first, resolves and checks ticket status, finds
the merge commit unambiguously, verifies it, confirms with the operator, checks the working tree is
clean, and only then reverts. Any ambiguity (zero or multiple matches, subject mismatch, dirty tree,
declined confirmation) **stops** without mutating git state — a false positive is worse than a false
negative, because an operator can always revert manually but a bad revert is harder to undo.

**Run from the main repo root.** Running from a secondary worktree can give an unexpected `git log`
scope. The normative schema for `status.md` (the `status:` and `title:` fields read below) is
`context/harness-reference.md` § Tickets — cite it as the source of truth if the fields ever move.

All git commands are invoked as **argument lists**, never assembled by shell string concatenation.

## Step 0 — Validate the argument (FIRST — before any git command)

This is the security boundary and it runs before anything else. Validate the raw `$ARGUMENTS`
ticket token against this allow-list pattern:

```
^[0-9]{4}(-[a-z0-9-]+)?$
```

- An **empty** argument or one that does not match (e.g. `abc`, `12`, `../etc`) is a hard stop.
  Print an error and stop. **No git command runs.**

  ```
  Error: /rollback requires a four-digit ticket number (e.g. 0020 or 0020-slug)
  ```

- Extract the **four-digit prefix** by taking the first four characters. Discard any `-slug`
  suffix. This prefix (call it `XXXX`) is the only value used in the git-log searches below —
  e.g. argument `0020-rollback-skill` yields the search prefix `0020`.

A `--dry-run` flag may appear anywhere in the arguments; note whether it is present (used in
Step 7). No other flags are accepted.

## Step 1 — Resolve the ticket's `status.md`

Look for the ticket's status file in this order:

1. **Completed first:** `.tickets/completed/XXXX-*/status.md` (a delivered ticket is archived here).
2. **Active fallback:** `.tickets/XXXX-*/status.md`.

Branches:

- **Neither exists** → stop: `Error: no ticket found for XXXX`.
- **Both exist simultaneously** → this is a **partial-archive** state left by an interrupted
  `/deliver` (the merge may already have landed even though the active copy still reads
  `review-ready`). Do **not** guess. Warn and stop:

  ```
  Warning: ticket XXXX is in a partial-archive state (both active and completed status.md exist).
  The delivery may be incomplete. Complete or repair the delivery before rolling back.
  ```

- **Exactly one exists** → use it as the resolved `status.md` for the steps below.

## Step 2 — Require `status: done`

Read the `status:` field from the resolved `status.md`. If it is **not** `done`, the ticket was
never delivered, so there is nothing to revert. Warn and stop — **no git command runs**:

```
Warning: ticket XXXX is not delivered (status: <status>). Nothing to roll back.
```

## Step 3 — Read the ticket title

Read the `title:` field from the resolved `status.md`; it populates the standardized commit
message in Step 11. If `title:` is **missing or empty**, stop rather than commit a malformed
message:

```
Error: ticket XXXX has no title in status.md — cannot build the rollback commit message.
```

## Step 4 — Find the merge commit (unambiguous)

Search git history for the merge commit that delivered this ticket. Use `--merges` to restrict to
merge commits, grep for the ticket branch string, and request a format that prints **exactly one
full commit hash per line** (never `--oneline`, whose extra columns invite whitespace-splitting
ambiguity when counting matches):

```
git log \
    --merges \
    --grep "ticket/XXXX" \
    --pretty=format:"%H"
```

Count the output lines (each is one full SHA):

- **Zero matches** → warn and stop. Non-standard merge messages (e.g. squash-and-merge) legitimately
  produce zero matches; direct the operator to revert manually:

  ```
  Warning: no merge commit found for ticket XXXX. If it was squash-merged, revert manually.
  ```

- **More than one match** → the result is ambiguous. **List every matching SHA** and stop:

  ```
  Error: multiple merge commits match ticket XXXX — refusing to guess:
    <sha-1>
    <sha-2>
  ```

- **Exactly one match** → keep that single SHA and continue.

## Step 5 — Verify the commit subject

Grep in Step 4 matches the whole commit message, including the body — so a body mention of another
ticket could produce a false hit. Fetch **only the subject line** of the single SHA and confirm it
contains the expected branch string:

```
git log -1 --pretty=format:'%s' <SHA>
```

If the subject does **not** contain `ticket/XXXX`, stop:

```
Error: commit subject does not match expected pattern — refusing to revert <SHA>.
```

## Step 6 — Show the operator the target

Before any revert (and as the body of the dry-run in Step 7), display the identified commit:

```
Rollback target for ticket XXXX:
  commit:  <SHA>
  subject: <full subject line>
```

## Step 7 — Dry-run short-circuit

If `--dry-run` was set (Step 0): the display in Step 6 **is** the entire output. Print it and
**exit** — run no git-mutating command and make no state change. Stop here.

## Step 8 — Confirm with the operator

Otherwise, prompt for explicit confirmation:

```
Revert this delivery? (yes/no)
```

Accept only an affirmative (`yes` / `y`). On **anything else** — including `no`, an empty answer,
or an unrecognized response — **exit without making any git change**. The working tree is left
exactly as it was.

## Step 9 — Clean-tree pre-flight (immediately before the revert)

Right before reverting, verify the working tree is clean so a revert can't entangle with unrelated
pending work:

```
git status --porcelain
```

If the output is **non-empty**, halt — **no git-mutating command runs**:

```
Error: Working tree is not clean — stash or commit pending changes before rollback.
```

## Step 10 — Execute the revert

Run the revert **without committing** so a standardized message can be applied. `-m 1` is required
for a merge commit — it selects the mainline (first) parent so the revert undoes the merged branch:

```
git revert --no-commit -m 1 <SHA>
```

**Mainline assumption:** `-m 1` presumes the delivery merge was made **from** `main` (i.e. `main` is
the merge's first parent), which is what `/deliver`'s `git merge --no-ff` produces. If a delivery
were ever made the other way (feature branch checked out, `main` merged into it), `-m 1` would
revert the wrong side — so this step is coupled to `/deliver` keeping `main` as the first parent.

If this command exits **non-zero** (e.g. a conflict because a later commit touched the same files),
**report the error and stop** — leave the partially-reverted index exactly as git left it. The skill
does not auto-abort; the operator decides:

```
Error: git revert hit a conflict. Resolve the conflicts manually, then run
  git revert --continue      (to finish the rollback)
or
  git revert --abort         (to discard it and restore the prior state).
```

## Step 11 — Commit with the standardized message

On a clean (zero-exit) revert, first confirm the revert actually staged an inversion. If the merge
was already reverted (or the revert produced no net change), the index is empty — do **not** create
an empty commit. Report and stop:

```
Notice: merge <SHA> appears already reverted — nothing to commit.
```

Otherwise commit the staged inversion. The message format is **exact** — the
character before `reverts` is a Unicode **em-dash** (U+2014), not a hyphen-minus or en-dash:

```
git commit -m "revert(ticket): XXXX <title> — reverts merge commit <SHA>"
```

`<title>` is the value read in Step 3; `<SHA>` is the verified merge commit. Because this revert
commit is **not** a merge commit, the `--merges` filter in Step 4 excludes it from any future
`/rollback` search — the rollback does not become a target for a subsequent rollback.

## Step 12 — Report

Confirm what happened: the reverted merge SHA, the new revert commit's subject, and a reminder that
the revert is itself reversible (`git revert` of the revert commit, or `git reset` before pushing)
if the rollback was a mistake.

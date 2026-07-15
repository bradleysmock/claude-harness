---
description: Ticket-aware git bisect helper — finds the commit that introduced a regression and names t
---
Ticket-aware `git bisect` helper — finds the commit that introduced a regression and names the ticket that introduced it. Drives `git bisect run` non-interactively and restores the repo on every exit path.

Execution is delegated to `bin/bisect-resolve.sh` — a **private implementation detail** of this command (not a shared utility). This command file is the user-facing contract; the script holds the tested logic.

**Output contract (UTF-8):** the final line uses a UTF-8 em-dash (U+2014, `—`):
`Regression introduced in commit <sha> — part of ticket XXXX (<title>)`, or
`Regression introduced in commit <sha> — not linked to a ticket`.

## Arguments

- `--good <ticket-or-ref>` — **required**. The last known-good boundary. A four-digit value (e.g. `0010`) is treated as a ticket number; any other value (SHA, `HEAD~5`, tag) is a raw git ref.
- `--bad <ticket-or-ref>` — optional, **default `HEAD`**. The known-bad boundary. Same resolution rules as `--good`.
- `--run <cmd>` — optional. The test command run at each bisect step. If omitted, it is resolved from configuration (see Step 3).

## Steps

1. **Validate and classify each boundary.** A ticket-number argument must match `^[0-9]{4}$` **before any use**. A value that is neither a four-digit ticket nor a valid git ref errors **before bisect starts** (no bisect state is created). Classification is delegated to `bin/bisect-resolve.sh classify-boundary`; a four-digit value resolves as a ticket, everything else as a git ref. Because every git call passes an argument list (never string interpolation), a payload such as `0010; echo pwned` is rejected at validation and never reaches a shell.

2. **Resolve ticket boundaries to merge commits.** A four-digit boundary is resolved to its delivery merge commit by scanning merge commits (`git log --merges`) and post-filtering the **subject line** with the anchored pattern `^[0-9a-f]+ Merge.*\bticket/XXXX-`. Anchoring to the subject prevents a false positive when another commit merely mentions the ticket in its body. If no merge commit matches the ticket number, the command errors with a clear message **before starting bisect**. Raw git refs are validated with `git rev-parse --verify`.

3. **Resolve the test command** (`bin/bisect-resolve.sh resolve-testcmd`), in precedence order:
   1. `--run <cmd>` if provided;
   2. the `test_command` key in `.claude/settings.json` if present;
   3. project auto-detect — `package.json` present ⇒ `npm test`; `pyproject.toml` containing a `[tool.pytest.ini_options]` or `[tool.pytest]` section ⇒ `pytest`. A `pyproject.toml` **without** a pytest section does **not** select `pytest`;
   4. otherwise error with guidance (pass `--run`, set `test_command`, or add a recognized manifest) **before starting bisect**.

4. **Prepare a single executable path.** `git bisect run` takes one executable path. A resolved command that contains whitespace (a multi-word command) is wrapped in a temporary script via `mktemp`; a single-word command is passed directly. The temporary script is deleted on cleanup.

5. **Install the cleanup guard first.** A single `trap 'git bisect reset || true' EXIT` is the **sole** cleanup path — there is no explicit post-run `git bisect reset`. It fires on every exit: success (where `git bisect run` exits 1 after finding the culprit), setup error, and interruption. The `|| true` prevents a double-fire "We are not bisecting" message when the repo is already reset. The same trap removes the temporary wrapper script.

6. **Run the bisect.** Start `git bisect` from the resolved good/bad boundaries, then `git bisect run <path>`. The test command's exit code drives the bisect automatically — `0` marks the revision good, non-zero marks it bad — with no operator input (`git bisect good` / `git bisect bad` are issued by `git bisect run`).

7. **Report the culprit.** Parse the first-bad commit SHA and report it (`bin/bisect-resolve.sh map-culprit`). Attribution uses **merge-commit ancestry traversal** as the primary mechanism:
   - If the culprit SHA is itself a merge commit targeting `ticket/XXXX-*`, attribute it directly.
   - Otherwise walk `git log --merges --ancestry-path <sha>..HEAD` to find the enclosing ticket merge commit — the one whose branch-side parent contains the culprit while its mainline parent does not.
   - Branch containment (`git branch -r --contains`) is **supplementary only**, never the sole mechanism (ticket branches are pruned by `/deliver`).

   The ticket title is read from the `title:` field of `.tickets/XXXX-*/status.md`. When `status.md` is absent or the `title:` field is missing, the output uses the bare ticket number (no title) rather than erroring. When no enclosing ticket merge commit is found — including a repo with no ticket merge commits at all — the command reports the raw SHA with `— not linked to a ticket`, without error.

## Guarantees

- The repo is never left detached-HEAD or mid-bisect on any exit path, including the normal success path where `git bisect run` exits 1.
- All shell commands use argument lists, never string interpolation (per the code generation rules).
- A repo with no ticket merge commits degrades gracefully to reporting the raw SHA.

## Example

```
/bisect --good 0010 --bad HEAD --run "pytest -x tests/"
```

Bisects between ticket 0010's merge commit and the current HEAD, wrapping the multi-word test command in a temporary script, and prints e.g.:

```
Regression introduced in commit a1b2c3d… — part of ticket 0012 (Dependency Freshness Gate)
```

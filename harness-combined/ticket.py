# harness-combined/ticket.py
"""Ticket state operations: number claiming, status transitions, owner.

Centralizes the git-backed ticket bookkeeping the markdown commands used to
inline by hand. Every mutation does its own scoped commit so ticket metadata
is never left uncommitted (the orphaned-update bug this module exists to kill).

Stdlib only. subprocess always called with argument lists.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

# ── harness-tickets coordination branch ────────────────────────────────────
# Ticket-number allocation and the coarse lifecycle log live on a dedicated
# orphan branch, never merged into `main`. `ledger.jsonl` is append-only, one
# JSON object per line; the next number is derived as max(claim.number)+1.
# origin's ref is the arbiter, so every mutation commits AND pushes before
# returning (§1a push invariant).
#
# NB: the design names this branch ".harness-tickets", but a git ref component
# may not begin with a dot (`git check-ref-format` rejects `refs/heads/.harness-
# tickets`), so the on-disk branch drops the leading dot: `harness-tickets`.
TICKETS_BRANCH = "harness-tickets"
LEDGER_FILE = "ledger.jsonl"
# Explicit refspec so `refs/remotes/origin/harness-tickets` is created/synced
# even on repos whose remote has no configured fetch refspec (`git remote add`).
_LEDGER_REFSPEC = f"+refs/heads/{TICKETS_BRANCH}:refs/remotes/origin/{TICKETS_BRANCH}"

# ── local same-machine claim lock (.tickets/.ticket.lock) ──────────────────
# Guards `claim()`'s number-scan-through-branch-creation critical section
# against concurrent same-machine claims (concurrent autopilots are routine);
# the ledger's push-first-wins race remains the cross-machine arbiter. Path
# and `pid:epoch` content format are unchanged from the prior hand-run Bash
# protocol — only the acquire/steal/heartbeat/release logic moved into Python.
_LOCK_STALE_SECONDS = 60
_LOCK_LIVE_RETRIES = 5
_LOCK_SLEEP_SECONDS = 2
_LOCK_MAX_ITERATIONS = 25


def find_tickets_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".tickets").is_dir():
            return candidate / ".tickets"
    raise FileNotFoundError(f"no .tickets/ found at or above {start}")


def _ticket_number(dir_name: str) -> int | None:
    head = dir_name[:4]
    return int(head) if head.isdigit() else None


def _scan_ticket_numbers(tickets_root: Path) -> list[int]:
    """Ticket numbers found by scanning `.tickets/*` and `.tickets/completed/*`.

    This is the *old* number source. It survives only to seed the ledger during
    one-time migration (`migrate`); live number allocation now derives from the
    ledger (`next_number`)."""
    numbers: list[int] = []
    for base in (tickets_root, tickets_root / "completed"):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            n = _ticket_number(child.name)
            if n is not None:
                numbers.append(n)
    return numbers


def next_number(repo: Path) -> int:
    """Next ticket number = max(claim.number in ledger) + 1.

    Reads `.harness-tickets:ledger.jsonl` (origin's ref when a remote exists,
    else the local ref), never the `.tickets/*` working tree. An absent ledger
    means no ticket has ever been claimed here → 1."""
    return _next_number(ledger_read(repo))


def format_number(n: int) -> str:
    return f"{n:04d}"


def _parse_status_lines(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def parse_status(status_md: Path) -> dict[str, str]:
    return _parse_status_lines(status_md.read_text(encoding="utf-8"))


def git(
    repo: Path,
    *args: str,
    check: bool = True,
    input: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = None
    if env is not None:
        run_env = {**os.environ, **env}
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        input=input,
        env=run_env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _commit(repo: Path, subject: str, *extra: str) -> None:
    """Make a commit with GPG signing disabled.

    Every commit this helper makes — the claim stub, status transitions, the
    reopen restore, and the delivery squash — is harness bookkeeping the ticket
    contract never signs. Disabling the signature (`-c commit.gpgsign=false`,
    a per-invocation override that never touches the repo's config) keeps these
    commits cheap and avoids hammering a per-commit signing hook under the far
    higher commit volume the ledger model introduces. (Ledger writes themselves
    use `commit-tree` plumbing, which is unsigned and worktree-free.)"""
    git(repo, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", subject, *extra)


def owner(repo: Path) -> str:
    proc = git(repo, "config", "user.email", check=False)
    return proc.stdout.strip()


def resolve_ticket_dir(tickets_root: Path, ident: str) -> Path:
    for base in (tickets_root, tickets_root / "completed"):
        if not base.is_dir():
            continue
        matches = sorted(p for p in base.glob(f"{ident}*") if p.is_dir())
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous ticket id {ident!r}: {[m.name for m in matches]}")
    raise FileNotFoundError(f"no ticket directory for {ident!r}")


def _rewrite_field(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[i] = f"{key}: {value}"
            found = True
            break
    if not found:
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def set_status(repo: Path, ident: str, new_status: str, *, push: bool = False) -> str:
    tickets_root = repo / ".tickets"
    ticket_dir = resolve_ticket_dir(tickets_root, ident)
    status_md = ticket_dir / "status.md"
    text = status_md.read_text(encoding="utf-8")
    text = _rewrite_field(text, "status", new_status)
    text = _rewrite_field(text, "updated", date.today().isoformat())
    status_md.write_text(text, encoding="utf-8")

    number = parse_status(status_md).get("ticket", ident)
    rel = ticket_dir.relative_to(repo)
    git(repo, "add", "--", str(rel))
    subject = f"chore(ticket): {number} → {new_status}"
    _commit(repo, subject)
    if push:
        _push_current_branch(repo)
    return subject


def _has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote", check=False).stdout.strip())


def _push_current_branch(repo: Path) -> bool:
    """Push HEAD's branch and report whether it is safe to proceed.

    Branch-only ticket states live on a worktree branch with no upstream yet —
    fall back to `push -u origin <branch>` so the first transition publishes the
    branch. Returns True when there is nothing to publish (no remote — local-only
    is expected) or the push succeeded; False only when a remote exists but the
    push was rejected, so destructive callers (delivery cleanup) can stop."""
    if not _has_remote(repo):
        return True
    proc = git(repo, "push", check=False)
    if proc.returncode == 0:
        return True
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    if branch and branch != "HEAD":
        return git(repo, "push", "-u", "origin", branch, check=False).returncode == 0
    return False


# ── ledger access layer (.harness-tickets) ─────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ledger(text: str) -> list[dict]:
    """Parse `ledger.jsonl` text into a list of event dicts. Blank and
    unparseable lines are skipped (append-only tolerance)."""
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def _dump_line(event: dict) -> str:
    """Serialize one ledger event to a single compact JSONL line."""
    return json.dumps(event, separators=(",", ":")) + "\n"


def _next_number(records: list[dict]) -> int:
    claims = [
        r["number"]
        for r in records
        if r.get("event") == "claim" and isinstance(r.get("number"), int)
    ]
    return (max(claims) + 1) if claims else 1


def _ledger_ref(repo: Path, remote: bool) -> str | None:
    """The ref to read the ledger from: origin's when a remote exists (it is the
    arbiter), else the local orphan branch. Returns None if neither exists."""
    candidates = (
        [f"origin/{TICKETS_BRANCH}", TICKETS_BRANCH]
        if remote
        else [TICKETS_BRANCH]
    )
    for ref in candidates:
        if git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0:
            return ref
    return None


def _show_ledger_text(repo: Path, ref: str) -> str:
    proc = git(repo, "show", f"{ref}:{LEDGER_FILE}", check=False)
    return proc.stdout if proc.returncode == 0 else ""


def ledger_read(repo: Path) -> list[dict]:
    """All ledger events, freshest known source. Does not fetch — callers that
    need the newest origin state fetch first (the txn helper does)."""
    remote = _has_remote(repo)
    ref = _ledger_ref(repo, remote)
    if ref is None:
        return []
    return _parse_ledger(_show_ledger_text(repo, ref))


def _create_orphan_ledger(repo: Path, remote: bool) -> None:
    """Create the orphan `.harness-tickets` branch with an empty `ledger.jsonl`
    via plumbing (no working-tree disturbance). When a remote exists the branch
    is created on origin (first-writer-wins — a rejected push means a concurrent
    writer created it first, so we just re-fetch)."""
    blob = git(repo, "hash-object", "-w", "--stdin", input="").stdout.strip()
    tree = git(repo, "mktree", input=f"100644 blob {blob}\t{LEDGER_FILE}\n").stdout.strip()
    commit = git(
        repo, "commit-tree", tree, "-m", "chore(harness-tickets): initialize ledger"
    ).stdout.strip()
    if remote:
        push = git(
            repo, "push", "origin", f"{commit}:refs/heads/{TICKETS_BRANCH}", check=False
        )
        git(repo, "fetch", "origin", _LEDGER_REFSPEC, check=False)
        _ = push  # a rejected push is fine: the fetch above adopts the winner
    else:
        git(repo, "update-ref", f"refs/heads/{TICKETS_BRANCH}", commit)


def ensure_tickets_branch(repo: Path, *, push: bool = True) -> None:
    """Guarantee the `.harness-tickets` orphan branch exists (bootstrap).

    Fetches origin's ref when a remote exists; creates the orphan (empty ledger)
    if absent. Idempotent — the `/init` bootstrap and every ticket op call it."""
    remote = push and _has_remote(repo)
    if remote:
        git(repo, "fetch", "origin", _LEDGER_REFSPEC, check=False)
    if _ledger_ref(repo, remote) is None:
        _create_orphan_ledger(repo, remote)


def _build_tree(repo: Path, base_sha: str, file_updates: dict[str, str]) -> str:
    """Build a new tree from `base_sha`'s tree with `file_updates` (repo-relative
    path → text content) added/replaced, using a throwaway index — no worktree,
    no checkout, no working-tree disturbance. Returns the new tree SHA."""
    index = Path(tempfile.mkdtemp(prefix="harness-tickets-idx-")) / "index"
    env = {"GIT_INDEX_FILE": str(index)}
    try:
        git(repo, "read-tree", base_sha, env=env)
        for path, content in file_updates.items():
            blob = git(repo, "hash-object", "-w", "--stdin", input=content).stdout.strip()
            git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        return git(repo, "write-tree", env=env).stdout.strip()
    finally:
        if index.exists():
            index.unlink()
        index.parent.rmdir()


def _tickets_txn(repo: Path, mutate, *, push: bool = True, max_retries: int = 5):
    """Run a mutation against the `harness-tickets` tree and publish it, honoring
    the §1a push invariant — via git **plumbing** (no worktree, no checkout, no
    signed commit), so the ledger's high write volume never hammers a per-commit
    signing hook or worktree admin.

    `mutate(records) -> (file_updates, result, subject)` returns the repo-relative
    files to add/replace on the coordination tree (append `ledger.jsonl`, snapshot
    ticket docs) or an empty/None `file_updates` for an idempotent no-op. It is
    re-invoked on every retry against the *newer* ledger, so a `claim` renumbers
    on a rejected push while an idempotent event simply re-applies on top."""
    remote = push and _has_remote(repo)
    delay = 0.02
    for _attempt in range(max_retries + 1):
        if remote:
            git(repo, "fetch", "origin", _LEDGER_REFSPEC, check=False)
        if _ledger_ref(repo, remote) is None:
            _create_orphan_ledger(repo, remote)
            if remote:
                git(repo, "fetch", "origin", _LEDGER_REFSPEC, check=False)
        base_ref = _ledger_ref(repo, remote)
        if base_ref is None:
            raise RuntimeError("_tickets_txn: harness-tickets ref unavailable")
        base_sha = git(repo, "rev-parse", base_ref).stdout.strip()
        records = _parse_ledger(_show_ledger_text(repo, base_ref))
        file_updates, result, subject = mutate(records)
        if not file_updates:
            return result  # idempotent no-op — nothing to write or push
        tree = _build_tree(repo, base_sha, file_updates)
        new_sha = git(
            repo, "commit-tree", tree, "-p", base_sha, "-m", subject
        ).stdout.strip()
        if not remote:
            git(repo, "update-ref", f"refs/heads/{TICKETS_BRANCH}", new_sha)
            return result
        pushed = git(
            repo, "push", "origin", f"{new_sha}:refs/heads/{TICKETS_BRANCH}", check=False
        )
        if pushed.returncode == 0:
            git(repo, "fetch", "origin", _LEDGER_REFSPEC, check=False)  # sync tracking ref
            return result
        # Rejected: a concurrent writer advanced origin/harness-tickets first.
        # Re-fetch and re-run mutate (claim renumbers; other events re-apply).
        time.sleep(delay)
        delay = min(delay * 2, 0.5)
    raise RuntimeError(f"_tickets_txn exhausted {max_retries} retries")


def ledger_append(repo: Path, build, *, push: bool = True, max_retries: int = 5):
    """Append events to the ledger and publish, honoring the §1a push invariant.

    `build(records)` returns `(events_to_append, result)`; re-invoked on every
    retry against the *newer* ledger. Empty `events_to_append` short-circuits."""

    def mutate(records: list[dict]):
        events, result = build(records)
        if not events:
            return None, result, ""
        # Every ledger line was written by `_dump_line`, so re-serializing the
        # parsed records reproduces the existing bytes; append the new events.
        new_text = "".join(_dump_line(r) for r in records + events)
        return {LEDGER_FILE: new_text}, result, _ledger_subject(events)

    return _tickets_txn(repo, mutate, push=push, max_retries=max_retries)


def _ledger_subject(events: list[dict]) -> str:
    head = events[0]
    event = head.get("event", "event")
    number = head.get("number")
    if isinstance(number, int):
        return f"chore(harness-tickets): {event} {format_number(number)}"
    return f"chore(harness-tickets): {event}"


def _write_stub(ticket_dir: Path, number_str: str, slug: str, title: str, who: str) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / "status.md").write_text(
        f"status: claimed\nticket: {number_str}\ntitle: {title}\n"
        f"branch: ticket/{number_str}-{slug}\nowner: {who}\n"
        f"source: local\nexternal_id:\nupdated: {date.today().isoformat()}\n",
        encoding="utf-8",
    )


def _create_branch_and_worktree(
    repo: Path, full_slug: str, slug: str, title: str, who: str, *, push: bool
) -> None:
    """Create branch ticket/<full_slug>, its worktree .worktrees/<full_slug>, and
    the `status: claimed` stub — all ON THE BRANCH, never on `main`.

    Called only AFTER the winning ledger claim push (create-after-push), so a
    renumber-on-reject never leaves an orphaned branch or worktree behind.
    Best-effort and idempotent: an existing branch (resume) is left as-is, and a
    stub already committed on the branch is not rewritten."""
    branch = f"ticket/{full_slug}"
    worktree = repo / ".worktrees" / full_slug
    if not git(repo, "branch", "--list", branch, check=False).stdout.strip():
        git(repo, "worktree", "add", str(worktree), "-b", branch, check=False)
    ticket_dir = worktree / ".tickets" / full_slug
    if (ticket_dir / "status.md").exists():
        return  # stub already present on the branch (resume)
    number_str = full_slug[:4]
    _write_stub(ticket_dir, number_str, slug, title, who)
    git(worktree, "add", "--", f".tickets/{full_slug}/")
    _commit(worktree, f"chore(ticket): {number_str} claim")
    if push and _has_remote(repo):
        _push_current_branch(worktree)


def _lock_path(tickets_root: Path) -> Path:
    return tickets_root / ".ticket.lock"


def _parse_lock_content(text: str) -> tuple[int, int] | None:
    """Parse `pid:epoch` lock content. Returns None for anything malformed —
    a non-integer field or a non-positive pid — which must never reach
    `os.kill`."""
    pid_str, _, epoch_str = text.partition(":")
    try:
        pid, epoch = int(pid_str), int(epoch_str)
    except ValueError:
        return None
    if pid <= 0:
        return None
    return pid, epoch


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_is_stale(parsed: tuple[int, int]) -> bool:
    pid, epoch = parsed
    return (int(time.time()) - epoch > _LOCK_STALE_SECONDS) or not _pid_alive(pid)


def _lock_capture(lock: Path, expected: str) -> bool:
    """Rename-verify steal/release primitive shared by the acquire loop and
    `_release_ticket_lock`. Renames *lock* to a per-own-pid temp and re-reads
    it: if the temp's content still matches *expected*, the capture succeeded
    (unlink the temp, return True) — the caller may proceed as if the lock
    were removed. If it differs, a fresh lock was recreated between the
    caller's observation and this rename; restore it non-clobberingly
    (`os.link` the temp back, `FileExistsError` means a third process's lock
    already occupies the path — just drop the temp) and report failure so the
    caller treats the lock as live rather than double-acquiring. A
    `FileNotFoundError` at the rename or the re-read means the lock/temp
    vanished under us — also a failed capture."""
    temp = lock.with_name(f"{lock.name}.stale-{os.getpid()}")
    try:
        os.rename(lock, temp)
    except FileNotFoundError:
        return False
    try:
        observed = temp.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    if observed == expected:
        temp.unlink(missing_ok=True)
        return True
    try:
        os.link(temp, lock)
    except FileExistsError:
        pass  # a third process's lock already occupies the path
    temp.unlink(missing_ok=True)
    return False


def _reap_stale_lock_temps(tickets_root: Path, lock: Path) -> None:
    """Self-heal orphaned `.ticket.lock.stale-<pid>` temps (left by a process
    killed mid-steal). A temp whose FILENAME-suffix pid is still alive is
    owned by a running steal-in-progress and is left untouched. Otherwise: if
    its content's pid is alive, restore the content to *lock* non-clobberingly
    (skipped if a live lock already occupies the path); either way, the temp
    itself is removed."""
    for temp in tickets_root.glob(".ticket.lock.stale-*"):
        suffix = temp.name.rsplit("-", 1)[-1]
        try:
            filename_pid = int(suffix)
        except ValueError:
            filename_pid = None
        if filename_pid is not None and filename_pid > 0 and _pid_alive(filename_pid):
            continue
        try:
            content = temp.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = _parse_lock_content(content)
        if parsed is not None and _pid_alive(parsed[0]) and not lock.exists():
            try:
                os.link(temp, lock)
            except FileExistsError:
                pass
        temp.unlink(missing_ok=True)


def _lock_timeout_error(lock: Path, raw_content: str) -> RuntimeError:
    parsed = _parse_lock_content(raw_content) if raw_content else None
    holder = f"pid {parsed[0]}" if parsed is not None else f"unknown holder (raw content: {raw_content!r})"
    return RuntimeError(f"timed out acquiring {lock} — held by {holder}")


def _acquire_ticket_lock(tickets_root: Path) -> None:
    """Atomically acquire `.tickets/.ticket.lock` (`O_CREAT|O_EXCL`), stealing
    a stale lock via the rename-verify primitive and retrying a live one up to
    `_LOCK_LIVE_RETRIES` times. A whole-loop ceiling of `_LOCK_MAX_ITERATIONS`
    bounds every path (steal attempts and live-retry sleeps combined) so an
    adversarial re-steal loop cannot spin forever."""
    tickets_root.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(tickets_root)
    live_retries = 0
    last_observed = ""
    for _iteration in range(_LOCK_MAX_ITERATIONS):
        _reap_stale_lock_temps(tickets_root, lock)
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()}:{int(time.time())}")
            return
        try:
            last_observed = lock.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue  # vanished mid-read — retry O_EXCL immediately
        parsed = _parse_lock_content(last_observed)
        if parsed is None or _lock_is_stale(parsed):
            if _lock_capture(lock, last_observed):
                continue  # lock is gone — retry O_EXCL immediately
            # a rename-verify race: someone else already resolved it this round
        live_retries += 1
        if live_retries > _LOCK_LIVE_RETRIES:
            raise _lock_timeout_error(lock, last_observed)
        time.sleep(_LOCK_SLEEP_SECONDS)
    raise _lock_timeout_error(lock, last_observed)


def _release_ticket_lock(tickets_root: Path) -> None:
    """Never raises — called from `finally`, so it can never mask a primary
    exception. A missing lock or a read error is a no-op (leaves the lock in
    place); ownership is checked via the same rename-verify primitive as
    steal, so a foreign lock (one this process no longer owns) is left
    untouched."""
    lock = _lock_path(tickets_root)
    try:
        current = lock.read_text(encoding="utf-8")
    except OSError:
        return
    parsed = _parse_lock_content(current)
    if parsed is not None and parsed[0] == os.getpid():
        _lock_capture(lock, current)


def _heartbeat_ticket_lock(tickets_root: Path) -> bool:
    """Refresh the lock's epoch if this process still owns it; called once per
    `_tickets_txn` retry/renumber iteration from `claim()`'s `build()`
    closure. Returns False (and warns to stderr) the moment ownership is lost
    — a missing lock or a foreign pid — so the caller stops heartbeating and
    the final release is skipped, never overwriting a successor's lock."""
    lock = _lock_path(tickets_root)
    try:
        current = lock.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"warning: {lock} vanished during heartbeat — lock ownership lost", file=sys.stderr)
        return False
    parsed = _parse_lock_content(current)
    if parsed is None or parsed[0] != os.getpid():
        print(
            f"warning: {lock} is no longer owned by this process (a successor "
            "holds it) — stopping heartbeat and skipping release",
            file=sys.stderr,
        )
        return False
    lock.write_text(f"{os.getpid()}:{int(time.time())}", encoding="utf-8")
    return True


class _LockOwnershipLost(RuntimeError):
    """Raised by `claim()`'s `build()` closure when heartbeat detects the lock
    was stolen mid-claim. Fail-closed: in a local-only repo (no remote) the
    ledger's `update-ref` has no compare-and-swap, so letting `build()` return
    a claim event anyway would let a second, now-concurrent claimant silently
    lose its update — exactly the double-claim bug this lock exists to
    prevent. Aborting before any ledger write is cheap and self-contained;
    `claim()`'s `finally` already skips `_release_ticket_lock` on this path,
    so the successor's lock is never touched."""


def claim(repo: Path, slug: str, title: str, *, push: bool = False, max_retries: int = 5) -> str:
    """Claim the next ticket number on `.harness-tickets` and open its branch.

    The number-allocation arbiter is the `claim` line in the ledger (not a `main`
    commit): append `claim`, commit + push `.harness-tickets` first-wins; on a
    rejected push, renumber against the newer ledger and retry (§1a). Only AFTER
    the winning push do we create the branch/worktree and write the `claimed`
    stub ON THE BRANCH. **No `main` commit.**

    Raises `_LockOwnershipLost` if a heartbeat during a retry/renumber iteration
    detects that a successor has stolen `.tickets/.ticket.lock` — this aborts
    before any ledger write, fail-closed against a lost double-claim guard."""
    who = owner(repo)
    ensure_tickets_branch(repo, push=push)

    tickets_root = repo / ".tickets"
    _acquire_ticket_lock(tickets_root)
    lock_owned = True

    def build(records: list[dict]) -> tuple[list[dict], str]:
        nonlocal lock_owned
        if lock_owned:
            lock_owned = _heartbeat_ticket_lock(tickets_root)
            if not lock_owned:
                raise _LockOwnershipLost(
                    f"claim() aborted: lock ownership of {_lock_path(tickets_root)} "
                    "was lost mid-claim (a successor now holds it)"
                )
        number = _next_number(records)
        full = f"{format_number(number)}-{slug}"
        event = {
            "event": "claim",
            "number": number,
            "slug": slug,
            "title": title,
            "owner": who,
            "branch": f"ticket/{full}",
            "ts": _now(),
        }
        return [event], full

    try:
        full_slug = ledger_append(repo, build, push=push, max_retries=max_retries)
        # Create-after-push: only the winning number reaches here.
        _create_branch_and_worktree(repo, full_slug, slug, title, who, push=push)
        return full_slug
    finally:
        if lock_owned:
            _release_ticket_lock(tickets_root)


def _fold_archive(repo: Path, slug: str) -> None:
    """Fold a staged ticket dir into the pending delivery commit.

    OS-mv the (staged) `.tickets/<slug>/` into `completed/`, rewrite its status →
    `done`, delete any `refine-touched.md` marker, then clear the staged old path
    and stage the archived one. Mirrors the archive pattern (OS mv + `git rm
    --cached` + `git add`) — never `git mv`, which is unsound against the index a
    `merge --squash` / `cherry-pick -n` leaves. The code changes already staged by
    the caller remain staged. Idempotent: a ticket already archived (dst present,
    src gone) is left as-is."""
    completed = repo / ".tickets" / "completed"
    completed.mkdir(parents=True, exist_ok=True)
    src = repo / ".tickets" / slug
    dst = completed / slug
    if src.is_dir() and not dst.exists():
        src.rename(dst)
    status_md = dst / "status.md"
    if status_md.exists():
        text = status_md.read_text(encoding="utf-8")
        text = _rewrite_field(text, "status", "done")
        text = _rewrite_field(text, "updated", date.today().isoformat())
        status_md.write_text(text, encoding="utf-8")
    (dst / "refine-touched.md").unlink(missing_ok=True)
    git(repo, "rm", "-r", "--cached", "--", f".tickets/{slug}/", check=False)
    git(repo, "add", "--", f".tickets/completed/{slug}/")


def _slug_number(slug: str) -> int | None:
    """Ticket number embedded in a `XXXX-<name>` slug, or None."""
    return _ticket_number(slug)


def _append_lifecycle(
    repo: Path, event: str, number: int, extra: dict | None = None, *, push: bool = True
) -> None:
    """Append a terminal/lifecycle event (`delivered`/`cancelled`/`abandoned`/
    `reopened`) idempotently by `(event, number)`, honoring the push invariant.

    Non-claim events keep their number across retries (a rejected push is just a
    concurrent append: re-fetch and re-apply on top of the newer ledger)."""

    def build(records: list[dict]) -> tuple[list[dict], None]:
        for r in records:
            if r.get("event") == event and r.get("number") == number:
                return [], None  # already recorded — idempotent
        line = {"event": event, "number": number}
        if extra:
            line.update(extra)
        line["ts"] = _now()
        return [line], None

    ledger_append(repo, build, push=push, max_retries=5)


def deliver_squash(repo: Path, branch: str, slug: str, title: str) -> str:
    """Deliver a ticket branch as a single squashed commit on the current branch.

    Under the `.harness-tickets` model this is the *first and only* time `main`
    sees the ticket. Mirrors the archive pattern (OS mv + `git rm --cached` +
    `git add`) — never `git mv`, which is unsound against the index `merge
    --squash` leaves. Folds the `→ done` transition and the `completed/` archive
    into the one squash commit, then appends a `delivered` ledger event."""
    if branch == TICKETS_BRANCH:
        raise RuntimeError(
            "deliver_squash: refusing to merge .harness-tickets into main "
            "(the coordination branch is never merged)."
        )
    # 1. Stage the whole branch diff (code + branch's .tickets/<slug>/) — no commit,
    #    and no merge commit, so commits-since-claim stays at one.
    git(repo, "merge", "--squash", branch)

    # 2-4. Fold the → done transition + completed/ archive into the pending commit.
    _fold_archive(repo, slug)

    # 5. One commit: full code diff + completed/<slug>/ at done, no .tickets/<slug>/.
    subject = f"feat: {slug} {title} (squash)"
    _commit(repo, subject)

    # 6. Publish `main` FIRST (the durable product record). Only on a successful
    #    publish do we destroy the worktree and branch — otherwise the squashed
    #    commit would survive only locally while its source history is deleted. On
    #    a rejected push, stop with everything intact so the lead can rebase and
    #    retry. `git branch -D` (not -d) because a squash leaves the branch without
    #    merge ancestry, so git never considers it "fully merged".
    if not _push_current_branch(repo):
        raise RuntimeError(
            f"deliver_squash: pushing the squashed commit to origin was rejected — "
            f"leaving the worktree and branch {branch!r} intact. Rebase onto the "
            f"updated main and retry the delivery."
        )
    # 7. Record delivery in the ledger (idempotent; main is already correct, so a
    #    ledger race never blocks delivery — the append simply retries).
    number = _slug_number(slug)
    if number is not None:
        sha = git(repo, "rev-parse", "HEAD").stdout.strip()
        _append_lifecycle(repo, "delivered", number, {"sha": sha})
    git(repo, "worktree", "remove", "--force", str(repo / ".worktrees" / slug), check=False)
    git(repo, "branch", "-D", branch, check=False)
    return subject


def _batch_worktree(batch_branch: str) -> str:
    """`.worktrees/` dir name for a batch branch: `batch/<slug>` → `batch-<slug>`
    (worktree dir names cannot carry the branch's `/`)."""
    return batch_branch.replace("/", "-", 1)


def deliver_squash_batch(
    repo: Path, batch_branch: str, members: list[dict[str, str]]
) -> list[str]:
    """Deliver a batch integration branch as one squashed commit *per member*.

    `members` is an ordered list of `{"slug", "title", "head"}`, where `head` is
    the boundary rev on `batch_branch` that ends that member's commit range. The
    last member's `head` should be batch HEAD so combined-critic repairs (made
    after the last member's build) fold into that member's commit.

    Each member's cumulative delta is cherry-picked (`-n`, so its per-source
    commits collapse to one) onto the current branch and committed as a single
    `feat: <slug> <title> (squash)` commit that also folds that member's
    `completed/<slug>/` archive at `done`. The commits publish in ONE push — so a
    batch is atomic on `main` — and only on a successful publish are the batch
    branch and every member's vestigial per-ticket branch/worktree removed. A
    cherry-pick conflict or a rejected push raises with everything intact
    (fail-closed), mirroring `deliver_squash`.

    Before any cherry-pick is attempted, every member's branch head is probed
    (read-only `git show`) for a `refine-touched.md` marker in its ticket
    directory. A marker means that member's design scope was machine-adjusted by
    a `/refine` pass and must never merge unseen into an atomic batch — a marked
    member at any position raises RuntimeError before the first cherry-pick, so
    no commit or index state is touched."""
    marked: list[str] = []
    for member in members:
        probe = git(
            repo, "show",
            f"{member['head']}:.tickets/{member['slug']}/refine-touched.md",
            check=False,
        )
        if probe.returncode == 0:
            marked.append(member["slug"])
    if marked:
        raise RuntimeError(
            f"deliver_squash_batch: member(s) {', '.join(marked)} carry a "
            "refine-touched.md marker (a /refine pass revised their design scope) "
            "and must not merge unseen into an atomic batch — deliver them "
            "individually via `/autopilot <slug>` after review. No cherry-pick "
            "was attempted; the batch branch and all member branches are intact."
        )

    subjects: list[str] = []
    prev = "HEAD"
    for member in members:
        slug, title, head = member["slug"], member["title"], member["head"]
        # Squash this member's range onto the delivery line. `cherry-pick -n` of a
        # rev range applies every commit in prev..head with no per-commit history.
        picked = git(repo, "cherry-pick", "--no-commit", f"{prev}..{head}", check=False)
        if picked.returncode != 0:
            git(repo, "cherry-pick", "--abort", check=False)
            raise RuntimeError(
                f"deliver_squash_batch: cherry-pick of member {slug!r} range "
                f"{prev}..{head} conflicted: {picked.stderr.strip()} — batch branch "
                f"{batch_branch!r} and all member branches left intact."
            )
        _fold_archive(repo, slug)
        subject = f"feat: {slug} {title} (squash)"
        _commit(repo, subject)
        subjects.append(subject)
        prev = head

    # Publish all N commits atomically. Only on a successful publish do we destroy
    # the source history — otherwise the squashed commits would survive only locally
    # while their branches are deleted. On a rejected push, stop with everything
    # intact so the lead can rebase and retry.
    if not _push_current_branch(repo):
        raise RuntimeError(
            f"deliver_squash_batch: pushing the {len(subjects)} squashed commit(s) to "
            f"origin was rejected — leaving the batch branch {batch_branch!r} and every "
            f"member branch intact. Rebase onto the updated main and retry the delivery."
        )

    # Record one `delivered` ledger event per member (idempotent; the batch is
    # already atomic on `main`, so a ledger race never blocks delivery).
    head_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    for member in members:
        number = _slug_number(member["slug"])
        if number is not None:
            _append_lifecycle(repo, "delivered", number, {"sha": head_sha})

    git(
        repo, "worktree", "remove", "--force",
        str(repo / ".worktrees" / _batch_worktree(batch_branch)), check=False,
    )
    git(repo, "branch", "-D", batch_branch, check=False)
    for member in members:
        slug = member["slug"]
        git(repo, "worktree", "remove", "--force", str(repo / ".worktrees" / slug), check=False)
        git(repo, "branch", "-D", f"ticket/{slug}", check=False)
    return subjects


# ── terminal lifecycle (main-free): cancel / abandon / reopen ──────────────

def _resolve_claim(repo: Path, ident: str) -> dict:
    """The most recent `claim` record matching `ident` (a bare number, a 4-digit
    id, or a full `XXXX-slug`)."""
    key = ident.strip()
    match: dict | None = None
    for r in ledger_read(repo):
        if r.get("event") != "claim":
            continue
        number = r.get("number")
        slug = r.get("slug", "")
        full = f"{format_number(number)}-{slug}" if isinstance(number, int) else ""
        if key in (str(number), format_number(number) if isinstance(number, int) else "", slug, full):
            match = r
    if match is None:
        raise FileNotFoundError(f"no claim in the ledger for {ident!r}")
    return match


def _full_slug_of(record: dict) -> str:
    return f"{format_number(record['number'])}-{record['slug']}"


def _branch_of(record: dict, full_slug: str) -> str:
    """The record's ledger branch, or the conventional `ticket/<full_slug>` when
    an older/migrated claim record lacks the field."""
    return record.get("branch", f"ticket/{full_slug}")


def _title_of(record: dict, full_slug: str) -> str:
    """The record's title, or `full_slug` itself when an older/migrated claim
    record lacks the field."""
    return record.get("title", full_slug)


def _read_ticket_docs(repo: Path, full_slug: str, branch: str) -> dict[str, str]:
    """Snapshot a ticket's docs (relpath → text) from its worktree if present,
    else from its branch ref. Empty when neither is available."""
    docs: dict[str, str] = {}
    worktree_dir = repo / ".worktrees" / full_slug / ".tickets" / full_slug
    if worktree_dir.is_dir():
        for path in sorted(worktree_dir.rglob("*")):
            if path.is_file():
                docs[str(path.relative_to(worktree_dir))] = path.read_text(encoding="utf-8")
        return docs
    listing = git(repo, "ls-tree", "-r", "--name-only", branch, f".tickets/{full_slug}/", check=False)
    if listing.returncode != 0:
        return docs
    prefix = f".tickets/{full_slug}/"
    for rel in listing.stdout.splitlines():
        rel = rel.strip()
        if not rel.startswith(prefix):
            continue
        blob = git(repo, "show", f"{branch}:{rel}", check=False)
        if blob.returncode == 0:
            docs[rel[len(prefix):]] = blob.stdout
    return docs


def _remove_branch_and_worktree(repo: Path, full_slug: str, branch: str, *, push: bool) -> None:
    git(repo, "worktree", "remove", "--force", str(repo / ".worktrees" / full_slug), check=False)
    git(repo, "branch", "-D", branch, check=False)
    if push and _has_remote(repo):
        git(repo, "push", "origin", "--delete", branch, check=False)


def _terminate(repo: Path, ident: str, event: str, *, push: bool = True) -> int:
    """Shared body for `cancel`/`abandon`: append the terminal ledger event AND
    archive the ticket docs onto `.harness-tickets` (under `<event>/<slug>/`) in
    one transaction, then remove the branch + worktree. **No `main` commit.**"""
    ensure_tickets_branch(repo, push=push)
    record = _resolve_claim(repo, ident)
    number = record["number"]
    full_slug = _full_slug_of(record)
    branch = _branch_of(record, full_slug)
    docs = _read_ticket_docs(repo, full_slug, branch)

    def mutate(records: list[dict]):
        if any(r.get("event") == event and r.get("number") == number for r in records):
            return None, number, ""  # idempotent
        line = {"event": event, "number": number, "slug": record["slug"], "ts": _now()}
        updates = {LEDGER_FILE: "".join(_dump_line(r) for r in records + [line])}
        for rel, content in docs.items():
            updates[f"{event}/{full_slug}/{rel}"] = content
        return updates, number, f"chore(harness-tickets): {event} {format_number(number)}"

    _tickets_txn(repo, mutate, push=push)
    _remove_branch_and_worktree(repo, full_slug, branch, push=push)
    return number


def cancel(repo: Path, ident: str, *, push: bool = True) -> int:
    """Cancel an in-flight ticket: `cancelled` ledger event + docs archived onto
    `.harness-tickets`; branch/worktree removed. Never touches `main`."""
    return _terminate(repo, ident, "cancelled", push=push)


def abandon(repo: Path, ident: str, *, push: bool = True) -> int:
    """Abandon an in-flight ticket (identical to cancel, distinct event)."""
    return _terminate(repo, ident, "abandoned", push=push)


def reopen(repo: Path, ident: str, *, push: bool = True) -> str:
    """Reopen a terminal ticket onto a fresh branch off `main` HEAD.

    Restores the ticket dir from its archive — `main`'s `completed/<slug>/` for a
    delivered ticket, else `.harness-tickets`'s `cancelled/`/`abandoned/` — sets
    `status: solution` on the branch, and appends a `reopened` ledger event."""
    ensure_tickets_branch(repo, push=push)
    record = _resolve_claim(repo, ident)
    number = record["number"]
    full_slug = _full_slug_of(record)
    branch = f"ticket/{full_slug}"
    who = record.get("owner", owner(repo))
    title = _title_of(record, full_slug)

    # Locate the archived docs: main's completed/ (delivered) else the ledger.
    docs: dict[str, str] = {}
    completed = repo / ".tickets" / "completed" / full_slug
    if completed.is_dir():
        for path in sorted(completed.rglob("*")):
            if path.is_file():
                docs[str(path.relative_to(completed))] = path.read_text(encoding="utf-8")
    else:
        ref = _ledger_ref(repo, _has_remote(repo))
        for event in ("cancelled", "abandoned"):
            if ref is None:
                break
            listing = git(repo, "ls-tree", "-r", "--name-only", ref, f"{event}/{full_slug}/", check=False)
            prefix = f"{event}/{full_slug}/"
            for rel in listing.stdout.splitlines():
                rel = rel.strip()
                if rel.startswith(prefix):
                    blob = git(repo, "show", f"{ref}:{rel}", check=False)
                    if blob.returncode == 0:
                        docs[rel[len(prefix):]] = blob.stdout
            if docs:
                break

    if not git(repo, "branch", "--list", branch, check=False).stdout.strip():
        git(repo, "worktree", "add", str(repo / ".worktrees" / full_slug), "-b", branch, check=False)
    worktree = repo / ".worktrees" / full_slug
    ticket_dir = worktree / ".tickets" / full_slug
    ticket_dir.mkdir(parents=True, exist_ok=True)
    if not docs:
        _write_stub(ticket_dir, full_slug[:4], record["slug"], title, who)
    for rel, content in docs.items():
        dst = ticket_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
    status_md = ticket_dir / "status.md"
    text = status_md.read_text(encoding="utf-8") if status_md.exists() else "status: solution\n"
    text = _rewrite_field(text, "status", "solution")
    text = _rewrite_field(text, "updated", date.today().isoformat())
    status_md.write_text(text, encoding="utf-8")
    git(worktree, "add", "-A")
    _commit(worktree, f"chore(ticket): {full_slug[:4]} → solution (reopened)")
    if push and _has_remote(repo):
        _push_current_branch(worktree)

    _append_lifecycle(repo, "reopened", number, {"slug": record["slug"]}, push=push)
    return full_slug


# ── migration: seed the ledger from the pre-existing .tickets/* tree ────────

def migrate(repo: Path, *, push: bool = True) -> int:
    """One-shot: seed `ledger.jsonl` from the existing `.tickets/*` (in-flight)
    and `.tickets/completed/*` (terminal) trees. Emits a `claim` per ticket and a
    `delivered`/`cancelled`/`abandoned` for terminal ones. Idempotent — a number
    already claimed in the ledger is skipped, so re-running never duplicates.
    Returns the count of events appended. Existing `main` claim stubs are left as
    history; the helper simply stops writing new ones."""
    ensure_tickets_branch(repo, push=push)
    who = owner(repo)
    scanned = _scan_for_migration(repo / ".tickets", who)

    def build(records: list[dict]) -> tuple[list[dict], int]:
        have_claim = {r["number"] for r in records if r.get("event") == "claim"}
        have_terminal = {
            (r.get("event"), r.get("number"))
            for r in records
            if r.get("event") in ("delivered", "cancelled", "abandoned")
        }
        events: list[dict] = []
        for entry in scanned:
            number = entry["number"]
            if number not in have_claim:
                events.append(
                    {
                        "event": "claim",
                        "number": number,
                        "slug": entry["slug"],
                        "title": entry["title"],
                        "owner": entry["owner"],
                        "branch": f"ticket/{number:04d}-{entry['slug']}",
                        "ts": _now(),
                    }
                )
            terminal = entry.get("terminal")
            if terminal and (terminal, number) not in have_terminal:
                events.append({"event": terminal, "number": number, "ts": _now()})
        return events, len(events)

    return ledger_append(repo, build, push=push)


def list_tickets(repo: Path) -> list[dict]:
    """Enumerate tickets for cross-cutting queries (`/sprint`, `/stale`,
    `/ticket-status`) from the ledger — NOT a `.tickets/*` scan on `main`, which
    no longer holds in-flight tickets.

    In-flight = a `claim` with no terminal (`delivered`/`cancelled`/`abandoned`)
    event; fine status/effort/depends-on are joined from the local worktree's
    `status.md` when present (else the coarse `claimed`). Delivered tickets are
    read from `main`'s `completed/<slug>/`. Each record:
    `{number, slug, title, status, owner, effort, depends_on, branch, completed}`."""
    records = ledger_read(repo)
    claims: dict[int, dict] = {}
    terminal: dict[int, str] = {}
    for r in records:
        ev, num = r.get("event"), r.get("number")
        if not isinstance(num, int):
            continue
        if ev == "claim":
            claims[num] = r
        elif ev in ("delivered", "cancelled", "abandoned"):
            terminal[num] = ev
        elif ev == "reopened":
            terminal.pop(num, None)  # reopened → back in flight

    out: list[dict] = []
    for num in sorted(claims):
        claim_rec = claims[num]
        slug = claim_rec.get("slug", "")
        full = f"{format_number(num)}-{slug}"
        term = terminal.get(num)
        if term == "delivered":
            continue  # surfaced from completed/ below, with its final docs
        fields: dict[str, str] = {}
        worktree_status = repo / ".worktrees" / full / ".tickets" / full / "status.md"
        if worktree_status.exists():
            fields = parse_status(worktree_status)
        out.append(
            {
                "number": format_number(num),
                "slug": slug,
                "title": fields.get("title", claim_rec.get("title", full)),
                "status": fields.get("status", term or "claimed"),
                "owner": fields.get("owner", claim_rec.get("owner", "")),
                "effort": fields.get("effort"),
                "depends_on": fields.get("depends-on", fields.get("depends_on", "")),
                "branch": claim_rec.get("branch", f"ticket/{full}"),
                "completed": term in ("cancelled", "abandoned"),
            }
        )

    completed_root = repo / ".tickets" / "completed"
    if completed_root.is_dir():
        for child in sorted(completed_root.iterdir()):
            n = _ticket_number(child.name) if child.is_dir() else None
            if n is None:
                continue
            status_md = child / "status.md"
            fields = parse_status(status_md) if status_md.exists() else {}
            out.append(
                {
                    "number": format_number(n),
                    "slug": child.name[5:] if len(child.name) > 5 else child.name,
                    "title": fields.get("title", child.name),
                    "status": fields.get("status", "done"),
                    "owner": fields.get("owner", ""),
                    "effort": fields.get("effort"),
                    "depends_on": fields.get("depends-on", fields.get("depends_on", "")),
                    "branch": fields.get("branch", f"ticket/{child.name}"),
                    "completed": True,
                }
            )
    return out


_STATUS_TO_TERMINAL = {"done": "delivered", "cancelled": "cancelled", "abandoned": "abandoned"}


def _scan_for_migration(tickets_root: Path, default_owner: str) -> list[dict]:
    """Scan `.tickets/*` and `.tickets/completed/*` into migration entries, sorted
    by number. Completed tickets carry a `terminal` event derived from status."""
    entries: dict[int, dict] = {}
    for base, completed in ((tickets_root, False), (tickets_root / "completed", True)):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            number = _ticket_number(child.name)
            if number is None:
                continue
            slug = child.name[5:] if len(child.name) > 5 else child.name
            fields: dict[str, str] = {}
            status_md = child / "status.md"
            if status_md.exists():
                fields = parse_status(status_md)
            entry = {
                "number": number,
                "slug": fields.get("branch", "").replace(f"ticket/{number:04d}-", "") or slug,
                "title": fields.get("title", slug),
                "owner": fields.get("owner", default_owner),
                "terminal": _STATUS_TO_TERMINAL.get(fields.get("status", "")) if completed else None,
            }
            entries[number] = entry
    return [entries[n] for n in sorted(entries)]


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: ticket <claim|set-status|owner|cancel|abandon|reopen|"
              "deliver|deliver-batch|ensure-branch|migrate|next-number> ...", file=sys.stderr)
        return 2
    repo = find_tickets_root(Path.cwd()).parent
    cmd = argv[0]
    if cmd == "owner":
        print(owner(repo))
        return 0
    if cmd == "set-status":
        push = "--push" in argv
        positional = [a for a in argv[1:] if not a.startswith("--")]
        print(set_status(repo, positional[0], positional[1], push=push))
        return 0
    if cmd == "claim":
        push = "--push" in argv
        positional = [a for a in argv[1:] if not a.startswith("--")]
        if len(positional) < 2:
            print("usage: ticket claim <slug> <title> [--push]", file=sys.stderr)
            return 2
        print(claim(repo, positional[0], positional[1], push=push))
        return 0
    if cmd == "deliver":
        positional = [a for a in argv[1:] if not a.startswith("--")]
        if not positional:
            print("usage: ticket deliver <ticket-id>", file=sys.stderr)
            return 2
        try:
            record = _resolve_claim(repo, positional[0])
            full_slug = _full_slug_of(record)
            branch = _branch_of(record, full_slug)
            title = _title_of(record, full_slug)
            docs = _read_ticket_docs(repo, full_slug, branch)
            if "status.md" not in docs:
                raise FileNotFoundError(f"no status.md found for {full_slug!r}")
            status = _parse_status_lines(docs["status.md"]).get("status", "")
            if status != "review-ready":
                print(
                    f"deliver: {full_slug!r} is at status {status!r}, not "
                    "'review-ready' — nothing delivered",
                    file=sys.stderr,
                )
                return 1
            print(deliver_squash(repo, branch, full_slug, title))
            return 0
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"deliver: {exc}", file=sys.stderr)
            return 1
    if cmd == "deliver-batch":
        positional = [a for a in argv[1:] if not a.startswith("--")]
        if len(positional) < 2:
            print(
                "usage: ticket deliver-batch <batch-branch> <members.json>",
                file=sys.stderr,
            )
            return 2
        batch_branch, members_path = positional[0], positional[1]
        members = json.loads(Path(members_path).read_text(encoding="utf-8"))
        for subject in deliver_squash_batch(repo, batch_branch, members):
            print(subject)
        return 0
    if cmd == "ensure-branch":
        push = "--push" in argv
        ensure_tickets_branch(repo, push=push)
        return 0
    if cmd == "migrate":
        push = "--push" in argv
        count = migrate(repo, push=push)
        print(f"migrated {count} ledger event(s)")
        return 0
    if cmd == "next-number":
        print(format_number(next_number(repo)))
        return 0
    if cmd == "list-json":
        print(json.dumps(list_tickets(repo)))
        return 0
    if cmd in ("cancel", "abandon", "reopen"):
        push = "--push" in argv
        positional = [a for a in argv[1:] if not a.startswith("--")]
        if not positional:
            print(f"usage: ticket {cmd} <ticket-id> [--push]", file=sys.stderr)
            return 2
        fn = {"cancel": cancel, "abandon": abandon, "reopen": reopen}[cmd]
        print(fn(repo, positional[0], push=push))
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

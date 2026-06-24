# Multi-Developer Ticketing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the harness `.tickets/` system safe for multiple developers on a shared `origin` and make orphaned (uncommitted) ticket updates structurally impossible.

**Architecture:** Introduce a small, testable Python module (`ticket.py`) that centralizes the three ticket operations the markdown commands currently inline by hand — number claiming, status transitions, and owner detection — each doing its own scoped commit. Add a Stop-hook guard that blocks the turn if any tracked `.tickets/` file is left uncommitted. Migrate the markdown command/flow files to call the helper, move implementation-phase status churn onto the ticket branch, and keep a coarse `claimed`/`implementing`/`abandoned`/terminal signal on `main`.

**Tech Stack:** Python 3.14 stdlib only (no new dependencies — matches existing `memory.py`/`dag.py`/`models.py` modules). `subprocess` with argument lists (never shell strings). `pytest` for tests. Markdown command/flow files drive the agent.

## Global Constraints

- **Git-native only.** No external service, no network dependency beyond `git push`/`pull` to the project's existing `origin`. (spec: "Stay git-native … A shared `origin` is the coordination point.")
- **No new Python dependencies.** Stdlib only. (matches existing harness modules)
- **subprocess uses argument lists, never shell concatenation.** (CLAUDE.md Code Generation Rules)
- **Ticket numbers are four-digit zero-padded** (`0001`): `f"{n:04d}"`.
- **Authoritative next number = `max(...)+1` scanning BOTH `.tickets/*` and `.tickets/completed/*`.** A number from an archived ticket is never reused. `NEXT_TICKET` is removed entirely.
- **`owner` is `git config user.email`.** Recorded in `status.md` at claim time.
- **TDD: write the failing test first, every task.**
- **Scoped commits only:** `git add .tickets/XXXX-<slug>/` — never `git add -A`. Lead-curated `_learnings.md`/`_standards.md` stay out.
- **`status.md` field order:** `status`, `ticket`, `title`, `branch`, `owner`, `source`, `external_id`, `updated`. `source` defaults to `local`; `external_id` defaults to empty. (GitHub seam — fields reserved, no code path built.)

---

## File Structure

**New files:**
- `harness-combined/ticket.py` — core module: `next_number()`, `claim()`, `set_status()`, `owner()`, status helpers.
- `harness-combined/bin/ticket` — thin CLI wrapper dispatching to `ticket.py` (sibling of existing `bin/harness-server`).
- `harness-combined/hooks/ticket_commit_guard.py` — Stop hook; blocks turn on uncommitted tracked `.tickets/` files.
- `harness-combined/tests/test_ticket_module.py` — unit tests for `ticket.py`.
- `harness-combined/tests/test_ticket_commit_guard.py` — unit tests for the guard hook.
- `harness-combined/tests/test_multidev_ticketing_docs.py` — content-verification tests for the markdown changes.
- `harness-combined/commands/abandon.md` — new `/abandon` command.

**Modified files:**
- `harness-combined/.claude-plugin/plugin.json` — add the guard hook to the `Stop` array.
- `harness-combined/commands/problem.md` — Phase 1 claim rewrite (helper, `claimed` status, owner, remove `NEXT_TICKET`).
- `harness-combined/context/flows/build-ticket.md` — `implementing` start-signal ordering + push; move `review-ready`/`changes-requested` commits onto the branch.
- `harness-combined/context/flows/deliver-ticket.md` — push transitions; document the status-merge behavior.
- `harness-combined/commands/cancel.md` — `--abandon` alias; release lock unchanged.
- `harness-combined/skills/status/SKILL.md` — `owner` column + stale-`implementing` flag.
- `harness-combined/commands/ticket-status.md` — `owner` column + stale flag (keep consistent with the skill).
- `harness-combined/context/harness-reference.md` — lifecycle table (`claimed`, `abandoned`), remove `NEXT_TICKET`, state-split note, `source`/`external_id`, committing section.

**Why a Python module instead of more markdown:** the orphan bug exists *because* status edits and their commits are two separate hand-run steps. Collapsing edit+commit into one tested function call is the fix; the guard hook is the backstop.

---

## Task 1: `ticket.py` — `next_number()` and status parsing

**Files:**
- Create: `harness-combined/ticket.py`
- Test: `harness-combined/tests/test_ticket_module.py`

**Interfaces:**
- Produces:
  - `find_tickets_root(start: Path) -> Path` — walk up from `start` to the dir containing `.tickets/`; raise `FileNotFoundError` if none.
  - `next_number(tickets_root: Path) -> int` — `max` over `tickets_root/*` and `tickets_root/completed/*` dir names whose first 4 chars are digits, `+1`; `1` if none.
  - `format_number(n: int) -> str` → `f"{n:04d}"`.
  - `parse_status(status_md: Path) -> dict[str, str]` — parse `key: value` lines into a dict.

- [ ] **Step 1: Write the failing test**

```python
# harness-combined/tests/test_ticket_module.py
from pathlib import Path
import ticket


def _mk(root: Path, name: str) -> None:
    (root / name).mkdir(parents=True)
    (root / name / "status.md").write_text("status: solution\n", encoding="utf-8")


def test_next_number_empty(tmp_path: Path) -> None:
    (tmp_path / ".tickets").mkdir()
    assert ticket.next_number(tmp_path / ".tickets") == 1


def test_next_number_scans_active_and_completed(tmp_path: Path) -> None:
    tickets = tmp_path / ".tickets"
    _mk(tickets, "0001-alpha")
    _mk(tickets, "completed/0007-archived")
    _mk(tickets, "0003-beta")
    assert ticket.next_number(tickets) == 8  # max(1,3,7)+1, completed counts


def test_format_number_zero_pads() -> None:
    assert ticket.format_number(8) == "0008"


def test_parse_status_reads_fields(tmp_path: Path) -> None:
    f = tmp_path / "status.md"
    f.write_text("status: implementing\nticket: 0008\nowner: a@b.c\n", encoding="utf-8")
    parsed = ticket.parse_status(f)
    assert parsed["status"] == "implementing"
    assert parsed["owner"] == "a@b.c"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_ticket_module.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ticket'`

- [ ] **Step 3: Write minimal implementation**

```python
# harness-combined/ticket.py
"""Ticket state operations: number claiming, status transitions, owner.

Centralizes the git-backed ticket bookkeeping the markdown commands used to
inline by hand. Every mutation does its own scoped commit so ticket metadata
is never left uncommitted (the orphaned-update bug this module exists to kill).

Stdlib only. subprocess always called with argument lists.
"""
from __future__ import annotations

from pathlib import Path


def find_tickets_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".tickets").is_dir():
            return candidate / ".tickets"
    raise FileNotFoundError(f"no .tickets/ found at or above {start}")


def _ticket_number(dir_name: str) -> int | None:
    head = dir_name[:4]
    return int(head) if head.isdigit() else None


def next_number(tickets_root: Path) -> int:
    numbers: list[int] = []
    search_dirs = [tickets_root, tickets_root / "completed"]
    for base in search_dirs:
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            n = _ticket_number(child.name)
            if n is not None:
                numbers.append(n)
    return (max(numbers) + 1) if numbers else 1


def format_number(n: int) -> str:
    return f"{n:04d}"


def parse_status(status_md: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in status_md.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd harness-combined && python -m pytest tests/test_ticket_module.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add harness-combined/ticket.py harness-combined/tests/test_ticket_module.py
git commit -m "feat(ticket): next_number scans active+completed, status parsing"
```

---

## Task 2: `ticket.py` — `owner()`, `set_status()` (atomic edit + scoped commit), and `bin/ticket` CLI

This is the core orphan fix: one call edits `status.md` **and** commits it.

**Files:**
- Modify: `harness-combined/ticket.py`
- Create: `harness-combined/bin/ticket`
- Test: `harness-combined/tests/test_ticket_module.py`

**Interfaces:**
- Consumes (Task 1): `find_tickets_root`, `parse_status`.
- Produces:
  - `owner(repo: Path) -> str` — `git -C <repo> config user.email`, stripped; `""` if unset.
  - `git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]` — run `git -C repo args`, capture text. Raise `RuntimeError` with stderr on nonzero (callers that tolerate failure pass `check=False`).
  - `resolve_ticket_dir(tickets_root: Path, ident: str) -> Path` — match `tickets_root/<ident>*` then `tickets_root/completed/<ident>*`; exactly one or raise.
  - `set_status(repo: Path, ident: str, new_status: str, *, push: bool = False) -> str` — rewrite the `status:` and `updated:` lines in that ticket's `status.md`, `git add` the ticket dir (scoped), commit `chore(ticket): <NNNN> → <new_status>`, optionally `git push`. Returns the commit subject. Commits in whatever branch `repo` is on (main checkout → main; worktree → branch).
  - CLI: `python ticket.py set-status <ident> <status> [--push]` and `python ticket.py owner`.

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_ticket_module.py
import subprocess


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    tdir = repo / ".tickets" / "0008-thing"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: solution\nticket: 0008\ntitle: Thing\n"
        "branch: ticket/0008-thing\nowner: dev@example.com\n"
        "source: local\nexternal_id:\nupdated: 2026-06-23\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def test_owner_reads_git_email(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert ticket.owner(repo) == "dev@example.com"


def test_set_status_edits_and_commits(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ticket.set_status(repo, "0008", "implementing")
    parsed = ticket.parse_status(repo / ".tickets" / "0008-thing" / "status.md")
    assert parsed["status"] == "implementing"
    # working tree is clean — nothing orphaned
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert porcelain.strip() == ""
    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert subject == "chore(ticket): 0008 → implementing"


def test_set_status_scopes_add(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "unrelated.txt").write_text("dirty", encoding="utf-8")  # untracked, must stay untracked
    ticket.set_status(repo, "0008", "review-ready")
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "unrelated.txt" in porcelain  # NOT swept into the commit
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_ticket_module.py -k "owner or set_status" -q`
Expected: FAIL — `AttributeError: module 'ticket' has no attribute 'owner'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to harness-combined/ticket.py
import subprocess
import sys
from datetime import date


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


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
    git(repo, "commit", "-m", subject)
    if push:
        git(repo, "push")
    return subject


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: ticket <set-status|owner|claim> ...", file=sys.stderr)
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
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
```

```bash
# harness-combined/bin/ticket  (mode 0755)
#!/usr/bin/env bash
exec python3 "$(dirname "$0")/../ticket.py" "$@"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && chmod +x bin/ticket && python -m pytest tests/test_ticket_module.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add harness-combined/ticket.py harness-combined/bin/ticket harness-combined/tests/test_ticket_module.py
git commit -m "feat(ticket): atomic set-status with scoped commit + bin/ticket CLI"
```

---

## Task 3: `ticket.py` — `claim()` with push-first-wins + renumber-on-conflict

**Files:**
- Modify: `harness-combined/ticket.py`
- Test: `harness-combined/tests/test_ticket_module.py`

**Interfaces:**
- Consumes: `next_number`, `format_number`, `owner`, `git`.
- Produces:
  - `claim(repo: Path, slug: str, title: str, *, push: bool = False, max_retries: int = 5) -> str` — fetch (if a remote exists), compute `XXXX`, write a stub `.tickets/XXXX-<slug>/status.md` (`status: claimed`, owner, source=local), `git add` it (scoped), commit `chore(ticket): XXXX claim`. If `push` and the push is rejected, `git pull --rebase`, recompute the number, `git mv` the stub to the new number, amend the commit, retry up to `max_retries`. Returns the claimed slug `XXXX-<slug>`. Raises `RuntimeError` if retries exhaust.

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_ticket_module.py
def _init_remote_clone(tmp_path: Path, name: str) -> tuple[Path, Path]:
    bare = tmp_path / "origin.git"
    if not bare.exists():
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    clone = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    subprocess.run(["git", "config", "user.email", f"{name}@x.c"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.name", name], cwd=clone, check=True)
    (clone / ".tickets").mkdir()
    (clone / ".tickets" / ".keep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=clone, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=clone, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=clone, check=True)
    return bare, clone


def test_claim_writes_stub_and_commits(tmp_path: Path) -> None:
    _, clone = _init_remote_clone(tmp_path, "alice")
    slug = ticket.claim(clone, "add-widget", "Add widget")
    status_md = clone / ".tickets" / slug / "status.md"
    parsed = ticket.parse_status(status_md)
    assert slug == "0001-add-widget"
    assert parsed["status"] == "claimed"
    assert parsed["owner"] == "alice@x.c"
    assert parsed["source"] == "local"


def test_claim_renumbers_when_number_taken_on_push(tmp_path: Path) -> None:
    bare, alice = _init_remote_clone(tmp_path, "alice")
    bob = tmp_path / "bob"
    subprocess.run(["git", "clone", "-q", str(bare), str(bob)], check=True)
    subprocess.run(["git", "config", "user.email", "bob@x.c"], cwd=bob, check=True)
    subprocess.run(["git", "config", "user.name", "bob"], cwd=bob, check=True)

    alice_slug = ticket.claim(alice, "alpha", "Alpha", push=True)   # wins 0001, pushed
    bob_slug = ticket.claim(bob, "beta", "Beta", push=True)         # must renumber to 0002
    assert alice_slug == "0001-alpha"
    assert bob_slug == "0002-beta"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_ticket_module.py -k claim -q`
Expected: FAIL — `AttributeError: module 'ticket' has no attribute 'claim'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to harness-combined/ticket.py
def _has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote", check=False).stdout.strip())


def _write_stub(ticket_dir: Path, number_str: str, slug: str, title: str, who: str) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / "status.md").write_text(
        f"status: claimed\nticket: {number_str}\ntitle: {title}\n"
        f"branch: ticket/{number_str}-{slug}\nowner: {who}\n"
        f"source: local\nexternal_id:\nupdated: {date.today().isoformat()}\n",
        encoding="utf-8",
    )


def claim(repo: Path, slug: str, title: str, *, push: bool = False, max_retries: int = 5) -> str:
    tickets_root = repo / ".tickets"
    who = owner(repo)
    remote = push and _has_remote(repo)
    if remote:
        git(repo, "fetch", "origin", check=False)

    number_str = ""
    for attempt in range(max_retries + 1):
        number_str = format_number(next_number(tickets_root))
        full_slug = f"{number_str}-{slug}"
        ticket_dir = tickets_root / full_slug
        _write_stub(ticket_dir, number_str, slug, title, who)
        git(repo, "add", "--", str(ticket_dir.relative_to(repo)))
        git(repo, "commit", "-m", f"chore(ticket): {number_str} claim")
        if not remote:
            return full_slug
        push_proc = git(repo, "push", check=False)
        if push_proc.returncode == 0:
            return full_slug
        # Someone claimed first. Rebase, drop our number, retry with a higher one.
        git(repo, "reset", "--hard", "HEAD~1", check=False)
        git(repo, "pull", "--rebase", check=False)
    raise RuntimeError(f"claim exhausted {max_retries} retries (last tried {number_str})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_ticket_module.py -k claim -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add harness-combined/ticket.py harness-combined/tests/test_ticket_module.py
git commit -m "feat(ticket): claim with push-first-wins and renumber-on-conflict"
```

---

## Task 4: Orphan-guard Stop hook

**Files:**
- Create: `harness-combined/hooks/ticket_commit_guard.py`
- Modify: `harness-combined/.claude-plugin/plugin.json`
- Test: `harness-combined/tests/test_ticket_commit_guard.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (self-contained; reads `payload["cwd"]` like `stop_full_gate.py`).
- Produces: `dirty_ticket_files(project_root: Path) -> list[str]` and `main(argv?) -> int`. Exit `2` + stderr message when dirty; exit `0` otherwise. No-op when there is no `.tickets/` or git is unavailable.

**Behavior:** at Stop, run `git -C <root> status --porcelain -- .tickets/` and report any line that is NOT untracked (`??`). Tracked modifications/staged-but-uncommitted ticket files block the turn. Untracked files (e.g. a brand-new uncommitted ticket dir) are *also* flagged, because a claimed ticket must be committed — match any line whose path is under `.tickets/` except the transient `.tickets/.ticket.lock` and `.tickets/.active` sentinels.

- [ ] **Step 1: Write the failing test**

```python
# harness-combined/tests/test_ticket_commit_guard.py
import subprocess
from pathlib import Path
import importlib.util

SPEC = importlib.util.spec_from_file_location(
    "ticket_commit_guard", Path(__file__).parent.parent / "hooks" / "ticket_commit_guard.py"
)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(guard)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "d@x.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "d"], cwd=repo, check=True)
    (repo / ".tickets" / "0001-x").mkdir(parents=True)
    (repo / ".tickets" / "0001-x" / "status.md").write_text("status: solution\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def test_clean_tree_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert guard.dirty_ticket_files(repo) == []


def test_uncommitted_status_edit_is_flagged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".tickets" / "0001-x" / "status.md").write_text("status: implementing\n", encoding="utf-8")
    assert any("0001-x/status.md" in f for f in guard.dirty_ticket_files(repo))


def test_lock_and_active_sentinels_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".tickets" / ".ticket.lock").write_text("123:1", encoding="utf-8")
    (repo / ".tickets" / ".active").write_text("0001-x", encoding="utf-8")
    assert guard.dirty_ticket_files(repo) == []


def test_no_tickets_dir_is_noop(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    assert guard.dirty_ticket_files(repo) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_ticket_commit_guard.py -q`
Expected: FAIL — `FileNotFoundError` / module load error (hook file does not exist yet)

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
# harness-combined/hooks/ticket_commit_guard.py
"""Stop hook: block turn-end if ticket metadata is left uncommitted.

Mirrors stop_full_gate.py's contract: exit 2 + stderr blocks completion. The
orphaned-update bug exists because status edits and their commits were two
separate hand-run steps; this guard makes leaving them uncommitted impossible.

No-op when there is no .tickets/ directory or git is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

IGNORED = {".tickets/.ticket.lock", ".tickets/.active"}


def dirty_ticket_files(project_root: Path) -> list[str]:
    if not (project_root / ".tickets").is_dir() or shutil.which("git") is None:
        return []
    proc = subprocess.run(
        ["git", "-C", str(project_root), "status", "--porcelain", "--", ".tickets/"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return []
    dirty: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()  # strip the 2-char status code + space
        if path in IGNORED:
            continue
        dirty.append(path)
    return dirty


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    project_root = Path(payload.get("cwd") or Path.cwd())
    dirty = dirty_ticket_files(project_root)
    if not dirty:
        return 0
    sys.stderr.write(
        "ticket_commit_guard blocked completion — uncommitted ticket metadata:\n\n"
        + "\n".join(f"  {p}" for p in dirty)
        + "\n\nCommit each ticket's metadata before ending the turn "
        "(use `ticket set-status <id> <status>` or a scoped `git add .tickets/<id>/`).\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_ticket_commit_guard.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire the hook into the plugin manifest**

In `harness-combined/.claude-plugin/plugin.json`, the `Stop` array currently holds one hook. Add the guard as a second entry so both run:

```json
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/stop_full_gate.py\""
          },
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/ticket_commit_guard.py\""
          }
        ]
      }
    ]
```

- [ ] **Step 6: Commit**

```bash
git add harness-combined/hooks/ticket_commit_guard.py harness-combined/tests/test_ticket_commit_guard.py harness-combined/.claude-plugin/plugin.json
git commit -m "feat(hooks): orphan-guard blocks turn on uncommitted ticket metadata"
```

---

## Task 5: `problem.md` Phase 1 — claim via helper, `claimed` status, remove `NEXT_TICKET`

This task changes markdown. The deliverable is verified by content-assertion tests (the repo's established pattern — see `tests/test_ticket_archiving.py`).

**Files:**
- Modify: `harness-combined/commands/problem.md` (Phase 1, lines ~23-41; Phase 2 `status.md` template ~74; Phase 5 commit ~228)
- Test: `harness-combined/tests/test_multidev_ticketing_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# harness-combined/tests/test_multidev_ticketing_docs.py
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── Task 5: problem.md claim phase ──────────────────────────────
def test_problem_claim_uses_helper() -> None:
    c = read("commands/problem.md")
    assert "ticket claim" in c or "ticket.py claim" in c


def test_problem_claim_sets_claimed_status() -> None:
    assert "status: claimed" in read("commands/problem.md")


def test_problem_records_owner() -> None:
    assert "owner:" in read("commands/problem.md")


def test_problem_no_longer_references_next_ticket() -> None:
    assert "NEXT_TICKET" not in read("commands/problem.md")


def test_problem_claim_pushes() -> None:
    c = read("commands/problem.md")
    assert "git push" in c or "--push" in c
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k problem -q`
Expected: FAIL — `assert 'status: claimed' in ...` and `NEXT_TICKET` still present.

- [ ] **Step 3: Rewrite Phase 1**

Replace the entire Phase 1 body (the numbered list, current lines ~27-41) with:

```markdown
Ticket number assignment must be atomic across developers. A claim is a small commit to `main` that is pushed immediately — first-push-wins; a loser re-numbers and retries. The claim commit is also the durable "work started / number taken" signal other developers see on `main`.

1. Acquire the local lock `.tickets/.ticket.lock` (format `pid:epoch`) exactly as before — it serializes multiple agents on *this* machine and avoids wasted round-trips. Treat a lock whose timestamp is >60s old or whose pid is dead (`kill -0 <pid>` nonzero) as stale and delete it; otherwise `sleep 2` and retry up to 5 times, then report the conflict.

2. Claim the number with the helper (it scans both `.tickets/*` and `.tickets/completed/*` for the next number, writes the stub `status.md` with `status: claimed` and `owner:` from `git config user.email`, commits `chore(ticket): XXXX claim`, and — when an `origin` exists — pushes; on a rejected push it rebases, re-numbers, and retries up to 5 times):

   `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" claim <slug> "<title>" --push`

   The command prints the claimed `XXXX-<slug>`. Record XXXX. If it exits non-zero after retries, stop and report the conflict to the lead.

3. Release the lock: `rm -f .tickets/.ticket.lock`.

The ticket directory now exists with a `claimed` stub. Phases 2–4 fill in `problem.md`, `requirements.md`, and `solution.md`.
```

Then in **Phase 2**, the `status.md` template (current line ~74) changes from `status: problem` to keep the helper-written fields. Replace the template block with:

```
status: solution
ticket: XXXX
title: <title>
branch: ticket/XXXX-<slug>
owner: <git config user.email>
source: local
external_id:
updated: YYYY-MM-DD
```

(Phases 2–4 advance the in-progress `claimed` stub through `problem`/`requirements`/`solution` by editing `status.md`; the final state committed at Phase 5 is `solution`.)

In **Phase 5**, change the commit block (current line ~228) from `git add .tickets/XXXX-<slug>/ .tickets/NEXT_TICKET` to:

```
git add .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX design (status: solution)"
git push    # publish the design so other developers see it; the claim commit was already pushed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k problem -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add harness-combined/commands/problem.md harness-combined/tests/test_multidev_ticketing_docs.py
git commit -m "docs(problem): claim via ticket helper, claimed status, drop NEXT_TICKET"
```

---

## Task 6: `build-ticket.md` — `implementing` start-signal ordering + branch-local build churn

The merge-safety fix: set `implementing` on `main` and push **before** creating the worktree, so the branch forks from the `implementing` commit and `review-ready`/`changes-requested` commits live only on the branch — making the eventual branch→main merge a clean fast-forward of `status.md`.

**Files:**
- Modify: `harness-combined/context/flows/build-ticket.md` (worktree/implementing block lines ~38-53; review-ready ~112-117; changes-requested ~184-188)
- Test: `harness-combined/tests/test_multidev_ticketing_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_multidev_ticketing_docs.py
def test_build_sets_implementing_before_worktree() -> None:
    c = read("context/flows/build-ticket.md")
    impl = c.index("status: implementing")
    wt = c.index("git worktree add")
    assert impl < wt, "implementing must be committed to main before the worktree is forked"


def test_build_pushes_start_signal() -> None:
    c = read("context/flows/build-ticket.md")
    seg = c[c.index("status: implementing"):c.index("git worktree add")]
    assert "git push" in seg


def test_build_review_ready_commits_on_branch() -> None:
    c = read("context/flows/build-ticket.md")
    assert "branch only" in c or "on the branch" in c
    # review-ready commit must run inside the worktree, not against main
    assert "git -C .worktrees/XXXX-<slug>" in c or "in the worktree" in c
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k build -q`
Expected: FAIL — `implementing` currently appears *after* `git worktree add`.

- [ ] **Step 3: Rewrite the worktree/implementing block**

Replace the current sequence (worktree add → set implementing → `.active` → commit, lines ~38-53) with this reordered block:

```markdown
First, set the start signal on `main` and publish it. This must happen **before** the worktree is created so the branch forks from the `implementing` commit (keeping the later branch→main merge a clean fast-forward of `status.md`):

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX implementing --push
```

Then create the worktree from the now-updated `main`:

```
git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug>
echo 'XXXX-<slug>' > .tickets/.active
```

From here, all implementation status churn (`review-ready`, `changes-requested`) is **branch only** — committed inside the worktree, never to `main`. `main` keeps showing `implementing` until `/deliver` merges the branch.
```

For the **review-ready** transition (current lines ~112-117), replace the `git add`/`git commit` against the main checkout with a worktree-scoped commit:

```markdown
Update `status.md` to `status: review-ready`. Commit it **in the worktree** (branch-local — it must not touch `main`):

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → review-ready"
```
```

Apply the same worktree-scoped pattern to the **changes-requested** transition (lines ~184-188):

```markdown
Update `status.md` to `status: changes-requested` and commit it in the worktree:

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → changes-requested"
```
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k build -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add harness-combined/context/flows/build-ticket.md harness-combined/tests/test_multidev_ticketing_docs.py
git commit -m "docs(build): implementing start-signal before worktree, branch-local churn"
```

---

## Task 7: `deliver-ticket.md` — push transitions, document status-merge

**Files:**
- Modify: `harness-combined/context/flows/deliver-ticket.md` (done transition ~62-65; archive commit ~76; rebase-downgrade ~116-119)
- Test: `harness-combined/tests/test_multidev_ticketing_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_multidev_ticketing_docs.py
def test_deliver_pushes_terminal_status() -> None:
    c = read("context/flows/deliver-ticket.md")
    seg = c[c.index('XXXX → done'):]
    assert "git push" in seg[:400]


def test_deliver_documents_status_merge() -> None:
    c = read("context/flows/deliver-ticket.md")
    assert "fast-forward" in c or "fast forward" in c
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k deliver -q`
Expected: FAIL — no `git push` near the done transition; no fast-forward note.

- [ ] **Step 3: Edit the flow**

After the `git commit -m "chore(ticket): XXXX → done"` line (~65), add a push and an explanatory note:

```markdown
```
git commit -m "chore(ticket): XXXX → done"
git push
```

> **Status merge:** the merged branch carries its `review-ready` `status.md`; because the branch forked from the `implementing` commit on `main` and only the branch advanced that file, the `--no-ff` merge fast-forwards `status.md` with no conflict. This `→ done` commit then sets the terminal state on `main`.
```

After the archive commit (`chore(ticket): XXXX archive → completed/`, ~76) add `git push`. After the rebase-downgrade commit (`YYYY → implementing (rebased onto main)`, ~119) add `git push`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k deliver -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add harness-combined/context/flows/deliver-ticket.md harness-combined/tests/test_multidev_ticketing_docs.py
git commit -m "docs(deliver): push terminal transitions, document status fast-forward"
```

---

## Task 8: `/abandon` command + `/cancel --abandon` alias

**Files:**
- Create: `harness-combined/commands/abandon.md`
- Modify: `harness-combined/commands/cancel.md` (resolution note + `--abandon` branch)
- Test: `harness-combined/tests/test_multidev_ticketing_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_multidev_ticketing_docs.py
def test_abandon_command_exists() -> None:
    assert (ROOT / "commands/abandon.md").exists()


def test_abandon_sets_abandoned_status() -> None:
    c = read("commands/abandon.md")
    assert "status: abandoned" in c or "→ abandoned" in c


def test_abandon_distinct_from_cancelled() -> None:
    c = read("commands/abandon.md")
    assert "started but dropped" in c or "dropped" in c


def test_cancel_supports_abandon_alias() -> None:
    c = read("commands/cancel.md")
    assert "--abandon" in c
    assert "abandoned" in c
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k abandon -q`
Expected: FAIL — `commands/abandon.md` does not exist.

- [ ] **Step 3: Create `commands/abandon.md`**

```markdown
Mark an in-flight ticket as `abandoned` — work was started but dropped (distinct from `cancelled`, which means a deliberate decision not to do the work). Frees the ticket for someone else to `/reopen` and signals on `main` that no one is actively driving it. This is `/cancel --abandon` with a dedicated, memorable name.

## Ticket Resolution

If a ticket number is provided, scan `.tickets/<arg>*/` then `.tickets/completed/<arg>*/`. Otherwise scan `.tickets/` for tickets whose status is `implementing`; if exactly one, use it, else list them and require the lead to choose.

## Steps

1. **Read `status.md`.** The status should be `implementing` (work was started but dropped). If it is `done`, `cancelled`, or `abandoned`, tell the lead and stop.

2. **Confirm with the lead.** Show what will happen: the worktree (if any) is removed, the branch deleted, `status.md` → `abandoned`, the `.active` sentinel cleared if it matches, and the ticket archived to `.tickets/completed/`. Stop if the lead declines.

3. **Remove the worktree** if `.worktrees/XXXX-<slug>` exists: `git worktree remove --force .worktrees/XXXX-<slug>`. Warn and continue on failure.

4. **Delete the branch** if it exists: `git branch -D ticket/XXXX-<slug>`. Warn and continue on failure.

5. **Clear sentinels:** `rm -f .tickets/.active` (if it names this ticket) and `rm -f .tickets/.ticket.lock`.

6. **Set status to abandoned** with the helper (atomic edit + scoped commit + push):

   `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX abandoned --push`

7. **Archive the ticket directory** to `.tickets/completed/` using the same mv + `git rm -r --cached` + `git add -- .tickets/completed/XXXX-<slug>/` + commit pattern as `/cancel` Step 8, then `git push`. Apply the same **Idempotency** and **Partial-move guard** rules. This is always a separate commit.

8. **Report completion.** Note the archive location and that `/reopen XXXX` resumes the ticket.
```

- [ ] **Step 4: Add the `--abandon` alias to `cancel.md`**

At the top of `cancel.md`, after the first sentence, add:

```markdown
With `--abandon`, the terminal status is `abandoned` instead of `cancelled` — use it when work was started but dropped rather than deliberately cancelled. (`/abandon` is the dedicated alias for this path.)
```

And in Step 7, note that under `--abandon` the helper is called with `abandoned` and the commit subject is `chore(ticket): XXXX → abandoned`:

```markdown
   Under `--abandon`, set `abandoned` instead: `python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX abandoned --push`.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k abandon -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add harness-combined/commands/abandon.md harness-combined/commands/cancel.md harness-combined/tests/test_multidev_ticketing_docs.py
git commit -m "feat(abandon): /abandon command + /cancel --abandon alias"
```

---

## Task 9: `/status` skill + `ticket-status` — owner column + stale-implementing flag

**Files:**
- Modify: `harness-combined/skills/status/SKILL.md` (Active Tickets table ~16-20)
- Modify: `harness-combined/commands/ticket-status.md`
- Test: `harness-combined/tests/test_multidev_ticketing_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_multidev_ticketing_docs.py
def test_status_skill_shows_owner() -> None:
    assert "owner" in read("skills/status/SKILL.md").lower()


def test_status_skill_flags_stale_implementing() -> None:
    c = read("skills/status/SKILL.md").lower()
    assert "stale" in c and "implementing" in c


def test_ticket_status_shows_owner() -> None:
    assert "owner" in read("commands/ticket-status.md").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k status -q`
Expected: FAIL — no `owner`/`stale` language yet.

- [ ] **Step 3: Edit the status skill**

In `skills/status/SKILL.md`, change the Active Tickets table header to include an Owner column, and add a stale note below it:

```markdown
### Active Tickets

| Ticket | Title | Status | Owner | Updated |
|--------|-------|--------|-------|---------|
| XXXX   | ...   | implementing / review-ready / ... | <owner from status.md> | <updated> |

> **Stale check:** flag any ticket in `implementing` whose `updated` date is more than 7 days old as a possible abandonment candidate (owner may have dropped it). Suggest `/abandon XXXX` or pinging the owner. Never abandon automatically.
```

Read `owner` and `updated` from each `.tickets/*/status.md`.

- [ ] **Step 4: Mirror the owner column into `ticket-status.md`**

Add an `Owner` column (read from `status.md`) to the active-tickets table in `commands/ticket-status.md`, consistent with the skill.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k status -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add harness-combined/skills/status/SKILL.md harness-combined/commands/ticket-status.md harness-combined/tests/test_multidev_ticketing_docs.py
git commit -m "docs(status): owner column + stale-implementing flag"
```

---

## Task 10: `harness-reference.md` — lifecycle, state-split, remove `NEXT_TICKET`, GitHub seam

**Files:**
- Modify: `harness-combined/context/harness-reference.md`
- Test: `harness-combined/tests/test_multidev_ticketing_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# add to harness-combined/tests/test_multidev_ticketing_docs.py
def test_reference_has_claimed_and_abandoned() -> None:
    c = read("context/harness-reference.md")
    assert "`claimed`" in c and "`abandoned`" in c


def test_reference_removes_next_ticket_counter() -> None:
    c = read("context/harness-reference.md")
    # The directory-listing line that documented NEXT_TICKET must be gone.
    assert "NEXT_TICKET        # Next available" not in c
    assert "max(existing" in c or "scans both" in c.lower() or "active and completed" in c.lower()


def test_reference_documents_state_split() -> None:
    c = read("context/harness-reference.md").lower()
    assert "branch only" in c or "branch-local" in c


def test_reference_documents_github_seam_fields() -> None:
    c = read("context/harness-reference.md")
    assert "source:" in c and "external_id:" in c


def test_reference_documents_owner_field() -> None:
    assert "owner:" in read("context/harness-reference.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k reference -q`
Expected: FAIL.

- [ ] **Step 3: Edit the reference**

1. In the `.tickets/` tree diagram, **remove** the `NEXT_TICKET` line and replace it with a comment that the next number is derived from existing directories:

```
.tickets/
  .ticket.lock       # Lock file — present only during a same-machine number claim (format: pid:epoch)
  .active            # Active session ticket slug (scopes stop hook)
  _standards.md
  _learnings.md
  XXXX-<slug>/
    ...
  completed/         # Archived tickets (status: done / cancelled / abandoned)
# Next number = max(XXXX over .tickets/* and .tickets/completed/*) + 1. No counter file.
```

2. Update the `status.md` format block to the new field set:

```
status: <stage>
ticket: XXXX
title: <short human-readable title>
branch: ticket/XXXX-<slug>
owner: <git config user.email>
source: local           # reserved seam — `github` etc. for externally-sourced tickets (not built)
external_id:            # reserved seam — e.g. github:#123
updated: YYYY-MM-DD
```

3. In the status-transition table, add rows for `claimed` (set by `/problem` Phase 1 claim → transitions to `solution`) and `abandoned` (set by `/abandon` or `/cancel --abandon` → reopened via `/reopen`). Note that `review-ready` and `changes-requested` are **branch-only** states.

4. Add a short subsection under **Tickets**:

```markdown
### State split (multi-developer)

`main` carries the coarse, durable signal — `claimed`, `solution`, `implementing` (work started), and the terminal `done` / `cancelled` / `abandoned`. The fine implementation-phase states (`review-ready`, `changes-requested`) are **branch only**: committed inside the worktree and merged to `main` at `/deliver`. Because `/build` commits `implementing` to `main` and pushes *before* forking the worktree, only the branch advances `status.md` afterward, so the branch→main merge fast-forwards it with no conflict.

`owner` (from `git config user.email`) is recorded at claim time. Number claiming is git-coordinated: a small `chore(ticket): XXXX claim` commit pushed first-wins; a loser re-numbers and retries. The `ticket.py` helper performs claims and transitions atomically (edit + scoped commit), and the `ticket_commit_guard` Stop hook blocks the turn if any tracked `.tickets/` file is left uncommitted.

**GitHub seam (reserved):** `source` / `external_id` exist so bug reports can later enter as tickets via GitHub Issues, behind the same `ticket.py` boundary. No network path is built in this iteration.
```

5. In the **Committing ticket metadata** section, remove the `.tickets/NEXT_TICKET` mention from the first-creation `git add` example.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd harness-combined && python -m pytest tests/test_multidev_ticketing_docs.py -k reference -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Full suite green**

Run: `cd harness-combined && python -m pytest -q`
Expected: PASS — all new tests plus the pre-existing `test_ticket_archiving.py` etc.

- [ ] **Step 6: Commit**

```bash
git add harness-combined/context/harness-reference.md harness-combined/tests/test_multidev_ticketing_docs.py
git commit -m "docs(reference): lifecycle, state-split, drop NEXT_TICKET, GitHub seam"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- Claim protocol (reserve-on-main, retry/renumber, scan both dirs) → Tasks 1, 3, 5.
- State split + lifecycle (`claimed`/`implementing`/`abandoned`, branch-local churn) → Tasks 5, 6, 7, 8, 10.
- Orphan cure (guard hook + atomic helper) → Tasks 2, 4.
- GitHub seam (`source`/`external_id`, all IDs via helper) → Tasks 2, 3, 10.
- Command/hook deltas (`/problem`, `/build`, `/deliver`, `/cancel`, `/abandon`, `/status`, Stop hook, reference) → Tasks 4–10.
- Success criteria: concurrent no-collision → Task 3 test `test_claim_renumbers...`; zero uncommitted ticket files → Task 4; coarse-on-main/fine-on-branch → Tasks 6, 7, 10; `owner` + stale → Tasks 5, 9; `source`/`external_id` default `local`, no GitHub path → Tasks 2, 3, 10. **All covered.**

**Placeholder scan:** no TBD/TODO; every code step shows complete code; every markdown edit is paired with a content-assertion test defining its contract. Clean.

**Type consistency:** `next_number`/`format_number`/`parse_status`/`owner`/`git`/`resolve_ticket_dir`/`set_status`/`claim` signatures are defined in Tasks 1–3 and consumed unchanged in later tasks' CLI invocations (`ticket.py claim …`, `ticket.py set-status …`). Hook function `dirty_ticket_files` defined and consumed in Task 4 only. Consistent.

**Note for the implementer — running git-backed tests:** the `ticket.py` tests shell out to real `git`. They set `user.email`/`user.name` per temp repo and use a bare repo as `origin` to exercise push-first-wins. No network. If `git`'s default branch name differs, the tests don't assume `main` vs `master` (they push `HEAD`).

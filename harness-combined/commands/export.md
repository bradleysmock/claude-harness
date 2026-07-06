Export ticket data from the `.tickets/` tree into portable JSON or CSV — for status reports, audits, or importing completed work into external tools.

Run the command from the project root (where `.tickets/` lives). It is read-only with respect to tickets and git history — it only reads `status.md` / `problem.md` / `solution.md`, queries `git log`, and writes to stdout or the `--output` file.

## Arguments

- `--format json|csv` — output format. **Default `json`.**
- `--all` — include tickets at every status. Without it, only completed tickets (`done`, `cancelled`) are exported.
- `--output <file>` — write to a file instead of stdout. A path that resolves **inside** the `.tickets/` tree is rejected before anything is written.

## Output schema

JSON field names and CSV column order are a fixed contract — external consumers depend on them:

`ticket, title, status, updated, branch, problem_summary, solution_summary, commits, commits_truncated`

- `problem_summary` — first paragraph after `## Problem` in `problem.md`; `null` (JSON) / empty (CSV) when absent.
- `solution_summary` — first paragraph after `## Approach` in `solution.md`; `null` / empty when `solution.md` or the heading is missing.
- `commits` — JSON: an array of `{hash, message}`; CSV: semicolon-joined `hash message` entries. Empty when the ticket branch is absent or deleted.
- `commits_truncated` — `true` when `git log` returned exactly 50 commits (the scan limit was hit), else `false`.

JSON output is a top-level array of objects, one per ticket. CSV output has a header row and quotes **every** field (`QUOTE_ALL`), so titles and summaries containing commas or newlines round-trip cleanly.

## Security

- Ticket directory names are validated against `^\d{4}-[a-z0-9-]+$` before use, so non-ticket entries (`completed`, `.ticket.lock`, `.active`) and any `../` / `;` / `$(...)` payload are skipped.
- Every `git` invocation passes an explicit argument list with `shell=False`; no ticket-derived value ever reaches a shell.
- The `--output` path is resolved and rejected if it lands inside `.tickets/`, so an export can never overwrite ticket state.

## Command

Run this script verbatim from the project root:

```python
#!/usr/bin/env python3
"""/export — extract .tickets/ data to JSON or CSV. Run from the project root."""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

TICKET_DIR_RE = re.compile(r"\d{4}-[a-z0-9-]+")
COMPLETED_STATUSES = frozenset({"done", "cancelled"})
COMMIT_LIMIT = 50
FIELDS = [
    "ticket", "title", "status", "updated", "branch",
    "problem_summary", "solution_summary", "commits", "commits_truncated",
]


def parse_status(path: Path) -> dict[str, str]:
    """Parse `key: value` lines from a status.md into a dict."""
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"(\w+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def first_paragraph_after(path: Path, heading: str) -> str | None:
    """Return the first non-blank paragraph after `heading`, or None if absent."""
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            idx = i + 1
            break
    if idx is None:
        return None
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    collected = []
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith("#"):
            break
        collected.append(stripped)
        idx += 1
    if not collected:
        return None
    return " ".join(collected)


def ticket_commits(branch: str) -> tuple[list[dict[str, str]], bool]:
    """Return (commits, truncated) for a ticket branch. Empty on any git failure.

    A `branch` value read from status.md is untrusted input. `shell=False` blocks
    shell metacharacters, but a value starting with '-' would be parsed by git as an
    *option* (e.g. `--output=<file>` writes an arbitrary file, bypassing the
    `--output` containment guard). Reject leading-'-' values and pass
    `--end-of-options` so nothing after it is ever treated as a flag.
    """
    if not branch or branch.startswith("-"):
        return [], False
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--first-parent",
             f"--max-count={COMMIT_LIMIT}", "--end-of-options", branch],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return [], False
    if result.returncode != 0:
        return [], False
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    commits = []
    for ln in lines:
        parts = ln.split(" ", 1)
        commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})
    return commits, len(lines) == COMMIT_LIMIT


def iter_ticket_dirs(root: Path) -> Iterator[Path]:
    """Yield validated ticket directories under `root` and `root/completed`."""
    bases: list[Path] = []
    if root.is_dir():
        bases.append(root)
    completed = root / "completed"
    if completed.is_dir():
        bases.append(completed)
    for base in bases:
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and TICKET_DIR_RE.fullmatch(entry.name):
                yield entry


def build_record(ticket_dir: Path) -> dict[str, object]:
    status_path = ticket_dir / "status.md"
    fields = parse_status(status_path) if status_path.is_file() else {}
    branch = fields.get("branch", "")
    commits, truncated = ticket_commits(branch)
    return {
        "ticket": fields.get("ticket", ""),
        "title": fields.get("title", ""),
        "status": fields.get("status", ""),
        "updated": fields.get("updated", ""),
        "branch": branch,
        "problem_summary": first_paragraph_after(ticket_dir / "problem.md", "## Problem"),
        "solution_summary": first_paragraph_after(ticket_dir / "solution.md", "## Approach"),
        "commits": commits,
        "commits_truncated": truncated,
    }


def to_json(records: list[dict[str, object]]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False)


def to_csv(records: list[dict[str, object]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(FIELDS)
    for r in records:
        commits_str = ";".join(
            f"{c['hash']} {c['message']}".strip() for c in r["commits"]
        )
        writer.writerow([
            r["ticket"], r["title"], r["status"], r["updated"], r["branch"],
            r["problem_summary"] if r["problem_summary"] is not None else "",
            r["solution_summary"] if r["solution_summary"] is not None else "",
            commits_str,
            "true" if r["commits_truncated"] else "false",
        ])
    return buf.getvalue()


def validate_output_path(output: str, tickets_root: Path) -> Path:
    resolved = Path(output).resolve()
    tickets_abs = tickets_root.resolve()
    if resolved == tickets_abs or tickets_abs in resolved.parents:
        print(f"export: refusing to write output inside {tickets_root}/", file=sys.stderr)
        raise SystemExit(2)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export", description="Export tickets to JSON or CSV.")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--all", action="store_true", dest="all_tickets")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    tickets_root = Path(".tickets")
    out_path = validate_output_path(args.output, tickets_root) if args.output else None

    records: list[dict[str, object]] = []
    for ticket_dir in iter_ticket_dirs(tickets_root):
        record = build_record(ticket_dir)
        if not args.all_tickets and record["status"] not in COMPLETED_STATUSES:
            continue
        records.append(record)
    records.sort(key=lambda r: (r["ticket"], r["branch"]))

    text = to_json(records) if args.format == "json" else to_csv(records)
    if not text.endswith("\n"):
        text += "\n"

    if out_path is not None:
        out_path.write_text(text, encoding="utf-8")
        print(f"export: wrote {len(records)} record(s) to {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

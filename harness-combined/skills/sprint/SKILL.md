---
name: sprint
description: Group open tickets into a time-boxed, dependency-ordered sprint plan. TRIGGER when the user asks to "plan a sprint", "build a sprint plan", "sequence the backlog", "how should we schedule the open tickets", or invokes /sprint (optionally with `--sprint-capacity N`, `--max-sprints N`, or `--as-of YYYY-MM-DD`). SKIP when the user wants the raw open-ticket list without scheduling (use /ticket-status), a single ticket's state (read its status.md), or a cycle-time retrospective over delivered work (use /velocity).
---

# Sprint skill — `/sprint`

Read every open ticket's `effort` and `depends-on` fields, treat completed
tickets as already-satisfied dependencies, and produce a Markdown sprint plan
that assigns tickets to dependency-ordered, capacity-bounded weekly sprints.

All ordering, bin-packing, and date math is delegated to
`${CLAUDE_PLUGIN_ROOT}/skills/sprint/compute.py` so the plan is **deterministic** —
the same backlog always yields the same schedule; LLM inference is never used
for the computation. This skill owns only the bash collection and the Markdown
rendering of the helper's JSON.

**Read-only guarantee:** this skill only *reads* `.tickets/*/status.md`. It must
never write, move, or delete any ticket artifact.

## Step 0 — Parse flags

Accept, in any order (all optional):

- `--sprint-capacity N` — effort points per sprint week (integer, default `6`).
- `--max-sprints N` — hard cap on planned sprints before overflow (integer, default `8`).
- `--as-of YYYY-MM-DD` — anchor date; Sprint 1 starts the Monday of the following
  week. Defaults to today's date (`date +%F`). Used to make output deterministic
  in tests.

Reject any unrecognised flag with a one-line usage message and stop.

## Step 1 — Collect ticket records (read-only, no `eval`)

Glob open tickets from `.tickets/*/status.md` (exclude `completed/`) and completed
tickets from `.tickets/completed/*/status.md`. For each, extract `ticket`,
`title`, `effort`, and `depends-on` with a fixed-field `grep`/`cut`, never by
parsing `ls`. Assemble the records into a JSON array with a Python one-liner so no
file-derived value is ever interpolated into a shell command string:

```bash
set -euo pipefail
field() { grep -m1 "^$2:" "$1" 2>/dev/null | cut -d: -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

emit() {  # $1 = status.md path, $2 = completed flag (true/false)
  local f="$1"
  python3 -c '
import json, sys
path, completed = sys.argv[1], sys.argv[2] == "true"
fields = {}
for line in open(path, encoding="utf-8"):
    if ":" in line:
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip()
print(json.dumps({
    "number": fields.get("ticket", ""),
    "title": fields.get("title", ""),
    "effort": fields.get("effort") or None,
    "status": fields.get("status", ""),
    "depends_on": fields.get("depends-on", ""),
    "completed": completed,
}))
' "$f" "$2"
}

records=()
for f in .tickets/*/status.md; do [ -e "$f" ] || continue; records+=("$(emit "$f" false)"); done
for f in .tickets/completed/*/status.md; do [ -e "$f" ] || continue; records+=("$(emit "$f" true)"); done
payload="$(printf '%s\n' "${records[@]}" | python3 -c 'import json,sys; print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))')"
```

Passing each `status.md` path (never its contents) to Python, and building the
JSON in Python rather than by shell concatenation, keeps attacker-influenceable
titles and `depends-on` values off the command line.

## Step 2 — Compute (JSON over stdin, never a shell arg)

Pipe the assembled payload to the helper over **stdin**, forwarding the parsed
flags:

```bash
echo "$payload" | python3 "${CLAUDE_PLUGIN_ROOT}/skills/sprint/compute.py" \
  --as-of "${AS_OF:-$(date +%F)}" \
  --sprint-capacity "${CAPACITY:-6}" \
  --max-sprints "${MAX_SPRINTS:-8}"
```

The helper writes a JSON plan object to stdout:

```
{"sprints": [{"n", "label", "tickets": [{"number","title","effort","effort_pts","status"}],
              "capacity_used", "capacity_total"}],
 "overflow": [{"number","title","reason"}],
 "warnings": [string]}
```

- **Exit code 1 with a `cycle` error on stderr** means a circular `depends-on`
  chain was found. Abort — do **not** render a partial plan. Report the cycle
  members from the error on a single line; surface no stack trace or internal path.
- **Exit code 1 with any other error** (malformed input, bad `--as-of`) → report the
  one-line error only.

## Step 3 — Render the Markdown plan

Parse the JSON and print:

**One section per sprint**, in order. Each section header is the sprint `label`
verbatim (e.g. `Sprint 1 — Week of 2026-06-22`), followed by a ticket table and a
capacity summary line:

```
### Sprint 1 — Week of 2026-06-22

| Ticket | Title | Effort | Status |
|--------|-------|--------|--------|
| 0035   | Sprint Planning Command | medium | solution |

Capacity: 2 / 6 points used.
```

**Backlog overflow** — if `overflow` is non-empty, a final `### Backlog overflow`
section with a table of `Ticket | Title | Reason`. Tickets land here when they
exceed the max-sprint cap or carry an unresolvable / self-referential dependency.

**Warnings** — if `warnings` is non-empty, list them under a `### Warnings`
heading (e.g. a ticket missing its `effort` field defaulted to medium, or an
excluded malformed `depends-on` token).

## Edge cases

- **No open tickets** → print exactly `No open tickets to plan.` and stop.
- **Every ticket in overflow** → still print the `Backlog overflow` and `Warnings`
  sections so the reason is visible; there simply are no sprint sections.
- **No stack traces or internal paths** on any error path — every failure surfaces
  as a single readable line.

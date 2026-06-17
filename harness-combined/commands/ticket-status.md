Generate a concise ticket status summary from the `.tickets/` directory.

## Step 1 — Read all status files

```bash
for f in .tickets/*/status.md; do echo "=== $f ==="; cat "$f"; done
for f in .tickets/completed/*/status.md; do echo "=== $f ==="; cat "$f"; done
```

Separate tickets by location and status:
- **Active tickets**: any ticket under `.tickets/` (not `completed/`) — these are open regardless of status value.
- **Completed tickets**: any ticket under `.tickets/completed/` — these are archived (status `done` or `cancelled`).

Collect each active ticket's number, title, and status string.

## Step 2 — Read problem.md for open tickets

```bash
for f in .tickets/*/problem.md; do echo "=== $f ==="; cat "$f"; done
```

From each open ticket's `problem.md`, extract:
- Any `## Dependencies` section listing other ticket numbers
- Scope signals: tickets touching migrations + multiple handlers + middleware are **large**; tickets adding a filter or extending one endpoint are **small**

## Step 3 — Output

Produce output in this exact structure — no preamble, no closing remarks:

### Open Tickets

| Ticket | Title | Status |
|---|---|---|
| NNNN | Title | `status` |

*(sorted ascending by ticket number)*

### Completed Tickets

| Ticket | Title | Status |
|---|---|---|
| NNNN | Title | `done` / `cancelled` |

*(sorted ascending by ticket number; omit section if no completed tickets)*

### Implementation Order

**Wave N — [short wave label]**
N. **NNNN** — one-line reason (size signal + dep note if relevant)

**Critical path:** `NNNN → NNNN → NNNN` — one sentence naming the bottleneck ticket.

## Ordering rules

1. **Status stage first** — `implementing` > `review-ready` > `requirements` > `solution` > `problem` > `open`. Tickets already in motion go first.
2. **Unblock others early** — if ticket A is a dependency of tickets B and C, A moves up.
3. **Small before large** — when two tickets have equal priority, the smaller one goes first.
4. **Wave labels** should be short and descriptive (e.g., "finish active work", "small unblocked extensions", "audit foundation", "capstone / depends on all above").

## Critical path

The longest dependency chain: `A → B → C` where each ticket is a dependency of the next. Follow with one sentence naming the end goal. If all tickets are independent, say: **Critical path:** none — all open tickets are independent.

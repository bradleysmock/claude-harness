Group the open backlog into a dependency-ordered, capacity-bounded sprint plan. Reads each open ticket's `effort` and `depends-on` fields (and treats completed tickets as already-satisfied dependencies), then prints a Markdown plan: one section per weekly sprint, a per-sprint ticket table with a capacity summary, plus a backlog-overflow section for anything that does not fit. **Read-only** — it never modifies any ticket artifact. This is a thin entry point; all logic lives in `skills/sprint/SKILL.md`.

## Usage

```
/sprint [--sprint-capacity N] [--max-sprints N] [--as-of YYYY-MM-DD]
```

- `--sprint-capacity N` — effort points per sprint week (default: `6`; `small=1`, `medium=2`, `large=3`).
- `--max-sprints N` — hard cap on planned sprints; anything beyond goes to backlog overflow (default: `8`).
- `--as-of YYYY-MM-DD` — anchor date. Sprint 1 starts the Monday of the following calendar week (default: today). Primarily for deterministic output.

All flags are optional; `/sprint` with no arguments produces a default plan.

## Dispatch

This command carries **no logic of its own**. Pass `$ARGUMENTS` through verbatim and load `skills/sprint/SKILL.md`, then follow that procedure exactly.

Flag parsing, the read-only bash collection of open + completed tickets, the deterministic ordering/bin-packing/date math in `skills/sprint/compute.py` (invoked with the ticket payload piped over **stdin**, never a shell argument), cycle-detection abort, and the Markdown rendering are all defined there — do not re-implement any of them here.

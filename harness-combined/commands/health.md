Render the harness health dashboard — a read-only, cross-ticket view of build quality.

Invoke the `health` skill. It runs `health.py` from the project root, which reads
`gate-findings.md` files from active and completed tickets and queries
`.harness/memory.db`, then prints a structured CLI report to stdout covering:

- **Gate pass rates** per gate type over the last 10 builds, with an `N of M builds
  analyzed` annotation.
- **Average repair cycles** per gate (from `memory.db`).
- **Top recurring failure modes** — the most frequent error codes (e.g. `B102`,
  `E501`, `TS2345`).
- **Tickets with the most gate failures**.
- **Trend indicators** per gate — improving / declining / stable.

Run it from the project root (where `.tickets/` lives). It is **strictly read-only** —
no file or database is written. It exits non-zero if the `.tickets/` directory cannot
be read.

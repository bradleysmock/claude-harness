# Helper: parse-gate-findings

**This is the reference contract for `learnings.py::parse_findings()`** — the
procedure below is implemented and unit-tested there, not executed as prose.
`/deliver` invokes it via the `learnings.py candidates <gate|critic> <ticket> <today>
<findings_path>` CLI (see `context/flows/deliver-ticket.md` Step 5); read this
document as the spec for that function's contract, not a runbook to re-derive by
hand.

Parse a ticket's findings file — `gate-findings.md` (`source_kind="gate"`) or
`critic-findings.md` (`source_kind="critic"`) — into a **normalized, sanitized
candidate-learnings list**. This produces *structured records* — never a
ready-to-write string. Sanitization happens **here, at the source**, for **both**
kinds (via `learnings.py::sanitize_pattern()`, shared with `parse-memory-findings.md`),
so the downstream `candidate-learnings-flow.md` never sees unsanitized content.

**Inputs**
- `findings_path` — the caller-resolved path to the findings file. The caller passes
  wherever the file currently lives: during `/build` that is
  `.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/<file>`; during `/deliver` the
  ticket has already been archived, so it is `.tickets/completed/XXXX-<slug>/<file>`.
  This helper does not assume a path — it reads whatever `findings_path` it is given.
- `source_kind` — `"gate"` (default) or `"critic"`. Selects the parser:
  `"gate"` reads the `/gate` output shape (Step 2), `"critic"` reads the persisted
  `critic-findings.md` round/escalation sections (Step 2c). Everything downstream —
  sanitization (Step 3), prioritization/cap (Step 4), return contract (Step 5) — is
  **identical** for both kinds; only the section walk and the `gate` field differ.
- `ticket_number` — the four-digit ticket number (e.g. `0005`).
- `today` — today's date as `YYYY-MM-DD`.

**Output** — a list of candidate records, each a plain object:

```
{ date, gate, ticket, pattern, severity }
```

This is **data**, not text destined for a write. The `pattern` field is already
sanitized and length-capped when it leaves this helper.

---

## Step 1 — Absent / empty short-circuit

If `findings_path` does not exist, return an **empty list**. Then, by `source_kind`:

- **`"gate"`** — if the file contains no `##` gate section with a `**Status**: FAIL`
  line, return an **empty list**.
- **`"critic"`** — if the file contains no `## Round` section carrying a `**BLOCKER**`
  or `**MAJOR**` finding, return an **empty list**.

The caller renders no section in that case (FR-8).

## Step 2 — Parse gate sections (tolerant) — `source_kind == "gate"`

`gate-findings.md` is written by `/gate` (see `commands/gate.md`) with this shape:

```markdown
## <gate-name>

**Status**: PASS | FAIL
**Duration**: NNNms

- `<file>:<line>` [`<code>`]: <message>
```

Walk each `## <gate-name>` section. Only `gate` (the heading) and `message` (the text
after the code, or the whole bullet if no code) are **required** — a section or bullet
missing either is **skipped**, not errored (gate-findings formats vary across gate
types and languages). For each failing finding, capture:

- `gate` — the section heading text (e.g. `lint`, `type_check`, `test`, `security`).
- `message` — the human-readable text of the bullet.
- `severity_signal` — the strongest severity token available, in this precedence:
  1. an explicit `BLOCKER` / `MAJOR` / `MINOR` / `OBS` token in the bullet, else
  2. an explicit `error` / `warning` token, else
  3. the section's `**Status**` (`FAIL` ⇒ treat as high-priority).
- `order` — source order (earlier lines are older; used only for recency ties).

Skip sections whose `**Status**` is `PASS` and skip `clean` bullets.

## Step 2c — Parse critic-report sections (tolerant) — `source_kind == "critic"`

`critic-findings.md` is written by `/build` Step 7/7a and `repair-escalation.md` (see
"Critic findings file" in `harness-reference.md`) with this shape — each finding's
header line is the exact literal grammar `critic-brief.md` Step 4 mandates
(`gates/critic_finding_parser.py` parses it structurally):

```markdown
## Round N — <date>

**BLOCKER** · <Panel> / <Dimension> · `<file>:<line>` <!-- harness-finding-key ... -->

<one-paragraph statement of the problem and the fix shape>

**MAJOR** · <Panel> / <Dimension> · `<file>:<line>` <!-- harness-finding-key ... -->

<one-paragraph statement of the problem and the fix shape>
```

Escalation diagnosis sub-sections (`### Escalation diagnosis — <date>`, nested under the
preceding `## Round` section) use `**Root cause**` / `**Fix strategy**` /
`**Target locations**` prose rather than BLOCKER/MAJOR findings; the diagnosis itself is
already captured in `memory.db` (FR-2) and yields no learnings candidates here. Walk each
`## Round` section and capture **only** its `**BLOCKER**`/`**MAJOR**` header lines (ignore
`**MINOR**`/`**OBS**`, any nested `### Escalation diagnosis` sub-section, and the
`Step 2.5` coverage recap). For each:

- `gate` — the **literal string `critic`** (never the round heading or date). This is
  the stable gate name that lets the memory records, dedup keys, and the rendered
  `_learnings.md` line all agree.
- `message` — the first sentence of the finding's body paragraph (the text following its
  header line, up to the next header or section end) — trimmed at the first `.`/`!`/`?`
  followed by whitespace or end-of-text, so a multi-sentence body doesn't blow the
  120-char cap in Step 3. Fall back to the full body text if it contains no sentence
  terminator. A finding whose body is empty is skipped, not errored.
- `severity_signal` — the explicit `BLOCKER` / `MAJOR` token (always high-priority here).
- `order` — source order (later rounds are more recent; used only for recency ties).

A section or finding missing a summary/message is **skipped, not errored** — the same
tolerance Step 2 applies to gate sections.

## Step 3 — Sanitize the pattern field (before it is ever emitted)

Derive `pattern` from `message`, then sanitize **in this order**. This is the trust
boundary — the text is attacker-influenceable (it can echo file contents or tool
output), so it is neutralized here, before any display or write:

1. **Strip heading lines** — remove any line beginning with `##`.
2. **Strip XML-like tags** — remove every `<...>` span (matching `<[^<>]*>`).
3. **Strip imperative directives to Claude** — remove any sentence phrased as an
   instruction addressed to the assistant (e.g. begins with `Claude,` / `Assistant,`
   / `Ignore` / `Disregard` / `You must` / `Now ` / `System:` and similar
   instruction framing). When in doubt, strip the sentence.
4. **Collapse newlines** — replace any newline with a single space.
5. **Restrict characters** — keep only printable alphanumerics + standard punctuation;
   drop control characters and other non-printables.
6. **Remove the field delimiter** — replace every `|` in the pattern with `/` (or a
   space). `|` is the `_learnings.md` column separator, so a pattern that contained one
   (e.g. a `X | None` type message) would otherwise inject a spurious field and break
   both the FR-1 line format and dedup. The pattern must contain **no** `|` when it
   leaves this helper.
7. **Length-cap** — truncate to **120 characters**.

If, after sanitization, `pattern` is **empty** (or only whitespace/punctuation),
**reject the candidate entirely** — do not emit it (FR-4).

## Step 4 — Assemble, prioritize, and cap

For each surviving finding, build a record:

- `date` = `today`
- `gate` = the parsed gate name
- `ticket` = `ticket_number`
- `pattern` = the sanitized string
- `severity` = `BLOCKER`/`MAJOR` when `severity_signal` is high-priority
  (`BLOCKER`, `MAJOR`, `error`, or `FAIL`), else `MINOR`/`OBS`.

Then order the records:

1. **Severity first** — high-priority (BLOCKER/MAJOR) before low-priority (MINOR/OBS).
2. **Recency next** — within a severity tier, most recent (higher `order`) first.

**Cap at 5.** When more than five candidates survive, keep the first five under this
ordering, so BLOCKER/MAJOR entries are retained ahead of MINOR/OBS (FR-1).

## Step 5 — Return

Return the (≤5) candidate records to the caller. The caller (`/deliver` or, indirectly,
`candidate-learnings-flow.md`) treats each record's `pattern` as already-safe: the
append string is later constructed **only** from these validated template fields
(`date`, `gate`, `ticket`, `pattern`) — never from the raw findings-file text (whether
`gate-findings.md` or `critic-findings.md`).

**No external calls.** This helper reads only the local findings file at
`findings_path` (NFR-2).

## Candidate line rendering

When a record is shown to the lead it is rendered as one ready-to-paste line:

```
<date> | <gate> | <ticket-number> | <pattern>
```

Rendering is the caller's concern; this helper guarantees every field is safe to place
into that template verbatim.

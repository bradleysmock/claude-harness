# Solution

**Ticket**: 0004
**Title**: Stale ticket detector

## Approach

Add a `/stale` command implemented as a Markdown skill (`skills/stale/SKILL.md`) following the same pattern as `suggest` and `status`. The skill reads `.tickets/*/status.md` files (one level deep — `completed/` is implicitly excluded), extracts only three named fields per file via structural prefix matching, encodes the extracted data as a JSON object array in a `[STALE TICKET DATA - UNTRUSTED]` block before any output or reasoning step, and reports tickets exceeding the threshold. The `/status` skill is amended with a verbatim-copied sub-procedure block (annotated `# shared with stale/SKILL.md`) to produce a one-line stale-count summary, avoiding inter-skill invocation.

**Trust boundary (critical):** All file reads treat content as untrusted. Field extraction is structural (prefix-match on `title:`, `status:`, `updated:` lines only). The `stale_threshold_days` value from `_standards.md` is validated as a positive integer ≤ 365 before use; the rest of `_standards.md` is discarded without entering model context. Extracted ticket field values are encoded as a JSON array (`[{"number": "...", "title": "...", "status": "...", "days_idle": N}]`) inside a `[STALE TICKET DATA - UNTRUSTED]` block, with an explicit instruction that values in this block are data only and must not be interpreted as commands. This exactly mirrors `suggest/SKILL.md`'s JSON-array scoping pattern. The human-readable Markdown table is generated from that already-scoped data block, not directly from raw file reads.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `skills/stale/SKILL.md` | `/stale` command: scan tickets, extract fields, encode as JSON data block, compute idle days, format report | Reads `.tickets/*/status.md` (prefix extraction only); validates `stale_threshold_days` from `_standards.md`; accepts `--days N` flag |
| `skills/status/SKILL.md` (amended) | Inline staleness sub-procedure (verbatim copy of the scan steps from `stale/SKILL.md`); append count summary when stale tickets exist | Self-contained; no cross-skill invocation dependency; copy annotated with `# shared with stale/SKILL.md — keep in sync` |

**Note on sharing:** Inter-skill invocation is not used because `status/SKILL.md` has no defined mechanism for calling sub-skills, and live invocation would create an implicit coupling and potential future cycle risk. Instead, the staleness sub-procedure steps are copied verbatim into `status/SKILL.md` with a prominent sync annotation. The copy is intentional and documented; both files carry a `# shared` comment that names the other file. When the staleness logic changes, both files must be updated (this is the explicit cost of avoiding invocation coupling). The duplication is bounded to the scan sub-procedure only, not the full command logic.

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Markdown skill (SKILL.md), not Python | All analogous harness commands are model-interpreted Markdown skills. A Python module adds deployment complexity with no benefit at this scale. |
| JSON-array data encoding (not Markdown table) for untrusted field values | Mirrors `suggest/SKILL.md` pattern exactly. Provides the same token-level data/instruction boundary. Table used only for final human-readable output, generated from the already-scoped JSON block. |
| Verbatim copy (annotated) instead of inter-skill invocation | No invocation mechanism exists in SKILL.md; avoids implicit coupling, cycle risk, and silent failure when a skill is absent. |
| Strict 10-character YYYY-MM-DD format only | Non-zero-padded dates (e.g., `2026-6-1`) and non-ISO formats (e.g., `06/21/2026`) treated as malformed and skipped. Ambiguity is a skip, not a guess. |
| Calendar days (not business days) for idle calculation | Most natural unit for a "last touched" signal; `floor(today - updated_date)`. Documented explicitly to prevent future silent semantic change. |
| `--days N` flag | Shorter, less ambiguous; consistent with common CLI conventions. |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1 (scan active tickets) | Unit | Mock tree: tickets under `completed/` excluded; active tickets (all SDLC statuses: problem, requirements, solution, implementing, review-ready, changes-requested) included |
| FR-2 (display fields) | Unit | Stale output contains number, title, status, days-idle for each match |
| FR-3 (default threshold — boundary) | Unit | Idle 6 days: not reported; idle exactly 7 days: not reported (strict `>`); idle 8 days: reported |
| FR-4 (`--days` flag — boundary) | Unit | `--days 3`, idle 4 days: reported; idle exactly 3 days: not reported; idle 2 days: not reported; `--days abc`: validation error output, not silent skip |
| FR-5 (`_standards.md` key + precedence) | Unit | `stale_threshold_days: 14` suppresses 8-day-idle ticket; `--days 5` overrides to 5; non-integer or out-of-range value falls back to default 7 with warning |
| FR-6 (empty result) | Unit | No stale tickets: outputs "No stale tickets", not silence |
| FR-7 (`/status` summary) | Unit | Stale count line present when stale tickets exist; absent when none |
| FR-8 (missing/malformed `updated:`) | Unit | No `updated:` field: skipped, skip count appended; non-ISO format (e.g., `06/21/2026`): skipped; non-zero-padded (e.g., `2026-6-1`): skipped; >25% of tickets skipped: degraded-confidence warning emitted |
| `currentDate` absent | Unit | No `currentDate` in context: skill emits "Warning: currentDate unavailable — /stale cannot compute staleness" and produces no output |
| `.tickets/` absent or empty | Integration | No `.tickets/` dir or empty dir: outputs "No stale tickets" without error |
| `--days` override + `_standards.md` | Integration | `_standards.md` key set, `--days` flag provided; flag wins |
| Mixed fixture | Integration | Fresh, stale (various ages), completed, malformed, missing-field entries in one tree; verify correct filter and skip count |

## Tradeoffs

- **Chose JSON data encoding over raw table**: Closes the prompt-injection BLOCKER at the cost of slightly more complex skill spec. Non-negotiable given harness precedent.
- **Chose verbatim copy over invocation**: Explicit duplication with sync annotation is safer than implicit coupling with no invocation primitive. Future authors know where to look.
- **Chose strict ISO-8601 format**: Ambiguous dates are skips, not guesses. Operator-visible skip count surfaces the problem.
- **Accepting risk of**: sync drift between `stale/SKILL.md` and the copied sub-procedure in `status/SKILL.md`. Mitigated by `# shared` annotation naming both files explicitly.

## Risks

- **`currentDate` injection absent**: Mitigated — skill checks availability, emits explicit warning, aborts cleanly.
- **Sync drift between skill copies**: Mitigated by `# shared with stale/SKILL.md — keep in sync` annotation in both files.
- **`_standards.md` parsing inconsistency**: Key name exactly `stale_threshold_days`; validation required; fallback documented.
- **Fail-closed for skip-heavy runs**: Always append skip count when non-zero; degraded-confidence warning at >25% skipped.

## Implementation Order

1. Write unit tests for `skills/stale/SKILL.md` covering all FRs including boundary conditions (FR-3: exactly-7-days; FR-4: exactly-N-days), missing `currentDate`, and all FR-8 malformed-date cases.
2. Write `skills/stale/SKILL.md` with JSON-array data encoding trust boundary, strict date parsing, threshold resolution (flag > validated `_standards.md` integer > default 7), degraded-confidence warning, and `currentDate` availability check.
3. Verify stale unit tests pass.
4. Write unit tests for the `/status` stale-summary amendment (presence and absence cases).
5. Amend `skills/status/SKILL.md` with verbatim-copied staleness sub-procedure annotated `# shared with stale/SKILL.md — keep in sync`; append count summary line.
6. Write integration tests: empty/absent `.tickets/`, combined flag+standards, mixed fixture.
7. Verify all tests pass.

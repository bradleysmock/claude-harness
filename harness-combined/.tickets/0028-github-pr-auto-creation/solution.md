# Solution

**Ticket**: 0028
**Title**: GitHub PR auto-creation

## Approach

Add a `--pr` flag to the deliver-ticket flow. When present: detect `gh` availability + auth, check for an existing open PR (by state), push the branch, open a PR with a body assembled from ticket artifacts, then merge locally. If `gh` is unavailable or unauthenticated, skip with a warning and proceed to merge.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `deliver.md` | Accept/forward `--pr`; warn + skip in spec mode | Reads `--pr` from `$ARGUMENTS` |
| `deliver-ticket.md` | Orchestrate flow; invoke sub-procedures; update confirm prompt | Calls guard + builder at step 3.5 |
| `gh_guard` (named block) | Install check; auth check; open-PR pre-check; TOCTOU catch; exit-code classification | In: branch + ticket; out: skip/proceed/stop + URL |
| `pr_body_builder` (named block) | Extract `## Approach`; build AC checklist; append ticket ref; write to `mktemp` file | In: ticket dir path; out: temp file path |

Named blocks have documented input/output contracts — testable without running the full deliver flow.

## Tech Choices

| Choice | Rationale |
|---|---|
| `command -v gh` | POSIX-standard; `which` behavior varies by OS |
| `gh pr view --json state --jq '.state'` == `"OPEN"` | Bare `gh pr view` exits 0 for any state; closed/merged PRs must not block creation |
| Double-quoted `"$TICKET_TITLE"` at call site | Hard constraint (CLAUDE.md "No shell concatenation"). Never assemble via string interpolation. |
| `mktemp` + `trap 'rm -f "$BODY_FILE"' EXIT` | Eliminates predictable-name race; `mktemp` failure → abort before push |
| awk extraction — no `END` block | `awk '/^## Approach$/{found=1;next} found && /^## /{exit} found{print}'`. `exit` skips `END` in some impls; adding an `END` block is prohibited. |
| AC checklist: first non-blank line per item | Multi-line AC items produce one checklist entry; avoids malformed indented continuations |
| Fail-stop on unexpected `gh pr create` error | Error message must distinguish push failure from PR-creation failure; include remote-branch recovery instructions |

## gh Exit-Code Classification

| Condition | Detection | Action |
|---|---|---|
| Not installed | `command -v gh` ≠ 0 | Skip + warn, continue |
| Not authenticated | `gh auth status` ≠ 0 | Skip + warn, continue |
| PR already open (pre-check) | state == `"OPEN"` | Print URL, skip create, continue |
| TOCTOU duplicate | `gh pr create` ≠ 0, stderr ~ "already exists\|already has" | Fetch + print URL, continue |
| Any other failure | `gh pr create` ≠ 0, no dup match | Stop, print error + recovery instructions |

## Test Plan

| Requirement | Type | Scenario |
|---|---|---|
| FR-1 | Unit | `--pr` parsed; absent → no PR path |
| FR-3 | Unit | Title with `"$\`` `;` → correctly quoted at call site |
| FR-4 | Unit | Approach present → in body; absent or file missing → placeholder, no error |
| FR-5 | Unit | AC → `- [ ] …` checklist; multi-line item → first line only; absent → placeholder |
| FR-6 | Unit | Body contains `Ticket: 0012` |
| FR-7 | Integration | `command -v gh` ≠ 0 → warn, continue |
| FR-8 | Integration | `gh auth status` ≠ 0 → warn, continue |
| FR-9 | Integration | `gh pr create` non-dup error → stop + recovery message |
| FR-10 | Integration | No `--pr` → functionally identical output |
| FR-11 | Integration | `--pr` → PR exists on remote, merge completes |
| FR-12 | Integration | Confirm prompt lists push + `gh pr create` when `--pr` active |
| FR-13 | Integration | Pre-check: state `"OPEN"` → skip, URL printed; state `"MERGED"` → create proceeds |
| FR-13 TOCTOU | Integration | Dup stderr → URL fetched, merge proceeds (not stop) |
| FR-14 | Integration | `--pr` in spec mode → warn, proceed |
| mktemp | Unit | `mktemp` fails → abort before push |

## Tradeoffs

- **PR before merge** — captures branch in pre-merge state; local merge remains delivery mechanism.
- **TOCTOU catch-and-continue** — operator intent was a PR; racing duplicate satisfies the goal.
- **Named blocks over separate files** — testable seams without filesystem fragmentation.
- **Accepting**: awk `exit` skips `END` in some impls — mitigated by prohibiting `END` blocks.

## Risks

- Duplicate-PR stderr pattern inferred from current `gh` CLI; a version change could fall through to hard-stop. Verify pattern against `gh` version at implementation time.
- Error message on hard stop must distinguish push failure from PR-creation failure to give accurate recovery instructions.

## Implementation Order

1. Update `deliver.md`: accept `--pr`, forward to ticket mode, warn + continue in spec mode.
2. Add `gh_guard` named block: install/auth checks, open-PR state check, TOCTOU catch, classification table. Unit tests first.
3. Add `pr_body_builder` named block: `mktemp` + `trap`, awk extraction, AC checklist, placeholders. Unit tests first.
4. Update Step 3 confirm prompt to list push + `gh pr create` when `--pr` active.
5. Insert push + PR creation between confirm and merge; distinguish push failure from PR-creation failure in error messages.
6. Integration tests: happy path, no-gh, no-auth, unexpected-failure, pre-check (open + merged), TOCTOU, no-`--pr`, spec-mode, injection-safe title, mktemp failure.

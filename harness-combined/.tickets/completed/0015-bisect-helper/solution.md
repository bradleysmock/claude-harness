# Solution

**Ticket**: 0015
**Title**: Bisect Helper

## Approach

Implement `/bisect` as a new command file (`commands/bisect.md`) that drives `git bisect` through Claude's Bash tool. The command resolves ticket numbers to merge commits via git log grep after validating ticket number format, runs `git bisect run` with a quoted test command, and maps the culprit commit back to a ticket via merge-commit ancestry traversal (not branch containment, which is unreliable after `/deliver` prunes branches). Cleanup (`git bisect reset`) runs on every exit path, including the normal exit-1 success path of `git bisect run`. No new Python code is needed — pure shell orchestration in a markdown command spec, consistent with all other harness commands.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `commands/bisect.md` | Command spec: argument parsing, validation, git resolution, bisect orchestration, cleanup | Bash tool: `git bisect`, `git log`, `git merge-base` |
| BisectBoundary resolver | Classify each boundary as TicketRef (4-digit number) or GitRef (any other value); resolve TicketRef to merge SHA via `git log --merges --oneline` post-filtered with a regex anchored to the subject line (`^[0-9a-f]+ Merge.*\bticket/XXXX-`); validate GitRef via `git rev-parse` | Emits merge commit SHA or errors before bisect starts; subject-anchored match prevents body-text false positives |
| Test command resolver | Determine test command: `--run` arg → `test_command` in `.claude/settings.json` → project-type auto-detect (package.json→npm test; pyproject.toml with `[tool.pytest]` or `[tool.pytest.ini_options]` section→pytest) → error with guidance. Multi-word `--run` values are wrapped in a temp script via `mktemp`; single-word values pass directly. | Emits a single executable path suitable for `git bisect run` |
| Bisect runner | Start `git bisect`, invoke `git bisect run <exec-path>` where exec-path is always a single-word path | `git bisect start/run/reset` |
| Culprit mapper | If culprit SHA is itself a merge commit targeting `ticket/XXXX-*`, attribute directly. Otherwise walk `git log --merges --ancestry-path <sha>..HEAD`. Extract ticket slug from merge subject. Read `title:` field from `.tickets/XXXX-*/status.md`; fall back to ticket number only when status.md absent or field missing. | Read-only git log + ticket directory scan |
| Cleanup guard | `trap 'git bisect reset || true' EXIT` at top of shell block. Remove explicit post-run reset to eliminate double-fire. `git bisect reset` via trap fires on all exits: success (exit 1 from git bisect run), error, SIGINT. | `|| true` prevents trap itself from exiting non-zero on a non-bisecting repo |

## Tech Choices

| Choice | Rationale |
|---|---|
| Markdown command spec (no new Python) | All harness commands are `.md` files; consistent pattern, zero added Python surface |
| `git bisect run` (not manual loop) | Native git automation; `git bisect run` terminates when a culprit is found (exit 1) or when the range is exhausted |
| Input validation before bisect start | McGraw: validate at trust boundary; ticket numbers must match `^\d{4}$` before use in grep; git refs validated via `git rev-parse` |
| Subject-anchored grep for merge commit resolution | `git log --merges --oneline` post-filtered with `^[0-9a-f]+ Merge.*\bticket/XXXX-` prevents body-text false positives where another ticket is mentioned in a PR description |
| Merge-commit ancestry traversal for attribution | Branch containment fails after `/deliver` prunes `ticket/XXXX-*` branches; ancestry traversal works from permanent merge commits on `main`; culprit-is-merge-commit edge case handled by checking whether the culprit SHA itself is a ticket merge commit |
| Multi-word `--run` wrapped in temp script | `git bisect run` requires a single executable path; multi-word commands wrapped in `mktemp` script, deleted on `trap EXIT`; single-word commands passed directly |
| `trap 'git bisect reset \|\| true' EXIT` only, no explicit reset | Sole cleanup path eliminates double-fire "We are not bisecting" stderr; `|| true` prevents trap-triggered non-zero exit on already-reset repo |
| pyproject.toml detection requires `[tool.pytest]` section | Presence of pyproject.toml alone does not imply pytest (poetry/flit/pdm/hatch use it too); section check prevents silent wrong-test-command corruption |
| `bin/bisect-resolve.sh` is private implementation detail | Extracted for testability only; documented as internal to `/bisect` to prevent accidental reuse creating a hard dependency |
| UTF-8 em-dash in output format; `LC_ALL=en_US.UTF-8` in tests | Explicitly chosen; integration tests set locale to avoid encoding mismatch in CI |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|---|---|---|
| FR-1/FR-2/FR-3 | Unit | 4-digit ticket number → TicketRef; "HEAD~3" → GitRef; "0010abc" → error before bisect |
| FR-4 | Unit | Subject-anchored regex returns correct merge SHA; body-text mention of ticket in other commit → not matched; no merge commit → error |
| FR-6 | Unit | `--run` overrides settings; settings key used when present; package.json → npm test; pyproject.toml with `[tool.pytest]` → pytest; pyproject.toml without pytest section → falls through to error; all absent → error with guidance |
| FR-7 | Unit | Multi-word `--run "pytest -x tests/"` → temp script created, deleted on cleanup; single-word → passed directly |
| FR-5/FR-7/FR-8 | Integration | Fixture repo (10 commits, regression at commit 7); bisect finds commit 7; `git bisect run` exit-1 treated as success; `trap` fires, repo HEAD restored |
| FR-10 | Integration | (a) Culprit is interior commit — ticket branch deleted post-merge; ancestry traversal finds enclosing merge commit. (b) Culprit is the merge commit itself; mapper recognizes and attributes directly. |
| FR-11 | Integration | Output format matches exactly (`LC_ALL=en_US.UTF-8`); SHA present; title from `status.md title:` field; "XXXX" (no title) when status.md absent; "not linked" when no ticket match |
| FR-12 | Integration | Cleanup: `git bisect reset` fires on success (exit-1 from bisect run), on setup error, on SIGINT simulation; no "We are not bisecting" stderr; repo HEAD matches pre-bisect ref after each |
| NFR-2 (injection) | Unit | Ticket number "0010; echo pwned" errors at validation step, never reaches git log |
| FR-9 | — | xref requirements.md FR-9 |

## Tradeoffs

- **Chose `git bisect run` over manual step loop**: atomic and handles all edge cases; `git bisect run` exit-1 is the documented success path (culprit found), not an error.
- **Chose merge-commit ancestry traversal over branch containment**: branch refs are deleted by `/deliver`; ancestry traversal works from permanent history; branch containment is supplementary only.
- **Chose mandatory test command resolution with error on ambiguity**: fail-closed is safer than guessing a test command that may corrupt bisect results; operator gets guidance, not a silent wrong answer.
- **Accepting risk of**: flaky test commands producing incorrect bisect attribution. Mitigation: document that test command must be deterministic; a future `--no-run` flag for manual step control is out of scope.

## Risks

- `git bisect run` exit semantics: exit 1 = culprit found (success), exit 125 = skip, exit 128+ = git error. The cleanup guard must not conflate these. Mitigation: cleanup via `trap EXIT` fires unconditionally; the exit-code interpretation logic is a separate post-bisect step.
- Repos with no merge commits (linear history): the ancestry traversal returns nothing; command falls through to "not linked to a ticket" without error. Tested via FR-10 edge case.
- Long bisect range: test command runs O(log N) times; document expected duration in command output preamble.

## Implementation Order

1. Write `commands/bisect.md` — argument spec, BisectBoundary classification (TicketRef vs GitRef), validation rules, multi-word `--run` wrapping contract, all exit paths named, cleanup via `trap` only.
2. Extract ticket-resolution and test-command-resolution logic into `bin/bisect-resolve.sh` (documented as private implementation detail of `/bisect`, not a shared utility) so FRs 1–7 can be unit-tested without a full bisect run.
3. Write unit tests: input validation; TicketRef/GitRef classification; subject-anchored merge commit grep (including body-text false-positive case); test-command resolution fallback chain (including pyproject.toml without `[tool.pytest]` section); multi-word `--run` temp-script creation.
4. Write integration test: fixture git repo (created programmatically), known regression at commit 7, full bisect run, assert culprit SHA and output format (`LC_ALL=en_US.UTF-8`).
5. Write post-merge attribution tests: (a) ticket branch deleted, ancestry traversal finds merge commit; (b) culprit is the merge commit itself, mapper attributes directly; (c) status.md absent → output uses ticket number without title.
6. Verify cleanup: `trap 'git bisect reset || true' EXIT` fires on success (exit-1), error, and SIGINT; no spurious stderr; repo HEAD matches pre-bisect ref.
7. Document output format contract (UTF-8, em-dash) in `commands/bisect.md` header and in the README command catalog.

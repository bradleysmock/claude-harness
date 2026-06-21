# Solution

**Ticket**: 0013
**Title**: Inline PR Comment Posting

## Approach

Add a `--comment` prose directive to the `/gate` command and to the `critique` skill. When set, the model calls `pr_commenter.post_findings(findings, worktree_root, should_post=True)`. That module probes `gh` availability and auth, detects the open PR, deduplicates against existing review comments, and submits all new findings as a single `gh api` batch. Each failure mode falls back to terminal output with a specific message. Requires Python >= 3.10 (for `match` on discriminated result types).

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `gates/finding.py` | `Finding(file, line, severity, code, message)` dataclass; `validate_finding(f, worktree_root: Path) -> bool` — precondition: `worktree_root` must be a canonicalized absolute `Path` (caller responsibility) | `Finding`, `validate_finding` |
| `gates/finding_parser.py` | Parse `gate-findings.md` (format: `- \`<file>:<line>\` [\`<code>\`]: <message>`) into validated `Finding` list; skip and log findings that fail validation | `parse_gate_findings(path, worktree_root) -> list[Finding]` |
| `gates/critic_finding_parser.py` | Parse critic prose structured as `**SEVERITY** · ... · \`<file>:<line>\`` + following paragraph; imports `Finding` from `gates/finding.py`; dedup key is `file:line:severity:code` (not message, since critic prose is non-deterministic) | `parse_critic_findings(text, worktree_root) -> list[Finding]` |
| `gates/pr_detector.py` | Probe `gh` binary (`FileNotFoundError`); probe `gh auth status`; call `gh pr view --json number,headRefName,headRefOid`; return `PR(number, head_ref, head_oid)` or `GhUnavailable(reason)`, `NotAuthenticated`, `NoPRFound` | `detect_pr() -> PR \| GhUnavailable \| NotAuthenticated \| NoPRFound` |
| `gates/comment_deduplicator.py` | Fetch existing review comments via `gh api /repos/.../pulls/{pr}/comments`; compute SHA-256 over dedup key per finding type (gate: `file:line:message`; critic: `file:line:severity:code`); return `set[str]` or `DeduplicationFailed(reason)` | `fetch_existing_hashes(pr_number, repo) -> set[str] \| DeduplicationFailed` |
| `gates/pr_commenter.py` | Entry point: resolves `worktree_root = Path(worktree_root).resolve()`; calls `pr_detector`; on `PR` result calls `comment_deduplicator`; on `set[str]` assembles `gh api` JSON payload; validates `headRefOid` matches `/^[0-9a-f]{40,64}$/` before use; posts; returns `PostResult(posted, skipped)` | `post_findings(findings, worktree_root, should_post, dry_run) -> PostResult` |
| `commands/gate.md` | Document `--comment` as an operator argument; describe `post_findings` step triggered | Prose update |
| `skills/critique/SKILL.md` | Document `--comment` in output step | Prose update |

## Result Types (pr_detector + comment_deduplicator)

```
PR(number: int, head_ref: str, head_oid: str)
GhUnavailable(reason: str)   # gh binary not found
NotAuthenticated(reason: str) # gh auth status non-zero
NoPRFound                     # gh pr view non-zero; no open PR for branch
DeduplicationFailed(reason: str) # fetch failed; abort to avoid duplicates
```

Behavior in `pr_commenter.py` orchestrator:
- `GhUnavailable` | `NotAuthenticated` | `NoPRFound` → terminal fallback with specific message
- `DeduplicationFailed` → terminal fallback with "aborting to avoid duplicates" message (distinct from above)

## Tech Choices

| Choice | Rationale |
|---|---|
| `gh api /repos/{owner}/{repo}/pulls/{pr}/reviews` JSON batch | Correct stable surface for multi-inline-comment review submission; `gh pr review` inline syntax is version-unstable |
| `headRefOid` validated against `/^[0-9a-f]{40,64}$/` | Explicit SHA validation before the value enters the API payload; fail-close to terminal if invalid |
| Dedup key: gate findings use `file:line:message`; critic findings use `file:line:severity:code` | Gate messages are deterministic across re-runs; critic messages are not — using a stable structural key for critics preserves the FR-5 dedup guarantee |
| `should_post: bool` parameter on `post_findings` | Creates a Python-level seam for FR-8 testing without needing a live model invocation; the model sets `should_post=True` when `--comment` is present |
| `PostResult(posted: int, skipped: int)` dataclass | Acceptance tests assert on field values (`result.posted == N`) not on the printed string format; the string is derived from the result at print time |
| Separated typed result types (`PR`, `GhUnavailable`, `NotAuthenticated`, `NoPRFound`, `DeduplicationFailed`) | Named for what happened, not what happens next; eliminates Hyrum's Law risk from `reason` string matching |
| Python >= 3.10 | `match` statement for discriminated result dispatch; document in `pyproject.toml` |
| Body size cap: assembled body > 60,000 chars → top-level summary comment | Fail-closed against GitHub's 65,535-char limit |

## Critic Finding Parser Grammar

`parse_critic_findings` targets this pattern produced by the `critic-brief.md` format:

```
**SEVERITY** · <Panel> / <Dimension> · `<file>:<line>`
<blank line>
<finding body paragraph>
```

Fallback: if no `` `file:line` `` token is found in the severity line, the finding is posted as a top-level PR comment (same as the off-diff fallback in FR-3). Test fixtures must include: (1) a BLOCKER with file:line; (2) a MINOR with no file:line; (3) a MAJOR where the file:line appears mid-sentence; (4) a critic output block with three findings of mixed severity.

## Failure Mode Handling

| Failure Mode | Behavior | Maps to FR |
|---|---|---|
| `GhUnavailable` | Print "gh not installed — outputting to terminal only"; fall back | FR-7 |
| `NotAuthenticated` | Print "gh not authenticated — outputting to terminal only"; fall back | FR-7 |
| `NoPRFound` | Print "No open PR for this branch — outputting to terminal only"; fall back | FR-6 |
| `DeduplicationFailed` | Print "Could not fetch existing comments — aborting to avoid duplicates; outputting to terminal only"; fall back | FR-5 |
| `headRefOid` invalid (not matching SHA regex) | Print "Invalid commit SHA from gh — aborting post; outputting to terminal only"; fall back | FR-3 |
| Inline comment rejected (line not in diff) | Post as top-level PR comment with filename + line in body | FR-3 |
| Assembled body > 60,000 chars | Post top-level summary listing finding IDs; direct to `gate-findings.md` | NFR-1 |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|---|---|---|
| FR-1 (PR detection) | Unit | No PR → `NoPRFound`; PR exists → `PR`; gh unavailable → `GhUnavailable`; not authed → `NotAuthenticated` |
| FR-2 (parse gate-findings) | Unit | Well-formed; `line` not integer → skipped; `file` outside worktree → skipped; empty file |
| FR-2 (parse critic findings) | Unit | BLOCKER with file:line; MINOR without file:line; MAJOR with mid-sentence file:line; three mixed findings |
| FR-3 (inline placement) | Integration | In-diff line → inline comment; off-diff line → top-level fallback |
| FR-4 (severity mapping) | Unit | BLOCKER/MAJOR → COMMENT inline; MINOR/OBS → COMMENT with `[suggestion]` prefix |
| FR-5 (deduplication — gate) | Unit | Matching `file:line:message` hash → skipped; different hash → posted |
| FR-5 (deduplication — critic) | Unit | Matching `file:line:severity:code` hash → skipped across re-renders |
| FR-5 (dedup fetch fail) | Unit | `DeduplicationFailed` → terminal fallback; no `gh api` post call |
| FR-6 (no PR fallback) | Unit | `NoPRFound` → terminal output, specific notice, zero `gh api` calls |
| FR-7 (gh unavailable) | Unit | `GhUnavailable` → specific message; `NotAuthenticated` → specific message |
| FR-8 (should_post seam) | Unit | `should_post=False` → zero `gh` subprocess calls; `should_post=True` → `post_findings` posts |
| FR-9 (batch submit) | Integration | 3 findings → exactly 1 `gh api` subprocess call |
| FR-10 (summary count) | Unit | `PostResult(posted=3, skipped=1)` → printed output contains "3" and "1" |
| Body size limit — under | Unit | 50 findings → inline batch path taken |
| Body size limit — over | Unit | 51 findings → top-level summary path taken |
| SHA validation | Unit | Non-SHA string from `headRefOid` → terminal fallback, no post |
| `worktree_root` resolution | Unit | Relative path input → `Path.resolve()` called before containment check |

## Tradeoffs

- **`gh api` batch over `gh pr review`**: stable API surface; requires resolving `headRefOid` separately. Acceptable given the SHA validation step added.
- **Typed result types over `Fallback(reason)`**: eliminates string-matching fragility and Hyrum's Law risk; cost is slightly more type definitions.
- **`should_post` bool seam**: makes FR-8 unit-testable without live model calls; the model sets `should_post=True` when the prose directive is present.
- **Separate dedup keys for gate vs critic findings**: maintains dedup guarantee for non-deterministic critic prose; cost is two hash strategies in one deduplicator.
- **Accepting risk of**: GitHub API schema drift on `reviews` endpoint — mitigated by explicit JSON key documentation and integration tests.

## Risks

- `headRefOid` must match `/^[0-9a-f]{40,64}$/`; on failure, fail-close to terminal. Validated in `pr_commenter.py` before payload assembly.
- Off-diff fallback top-level comments accumulate across re-runs if the hash key is stable. Confirmed: critic dedup key is structural (`file:line:severity:code`), so re-runs deduplicate correctly.
- Python >= 3.10 requirement — document in `pyproject.toml` `requires-python` field; gate will catch earlier versions.

## Implementation Order

1. Add `gates/finding.py` with `Finding` dataclass, typed result types, `validate_finding` — unit tests first.
2. Add `gates/finding_parser.py` (imports `Finding` from step 1) — unit tests first.
3. Add `gates/critic_finding_parser.py` (imports `Finding` from step 1; uses `file:line:severity:code` dedup key) — unit tests first including four fixture cases from the Critic Finding Parser Grammar section.
4. Add `gates/pr_detector.py` (returns `PR | GhUnavailable | NotAuthenticated | NoPRFound`) — unit tests first.
5. Add `gates/comment_deduplicator.py` (returns `set[str] | DeduplicationFailed`; handles both gate and critic key strategies) — unit tests first.
6. Add `gates/pr_commenter.py`: resolve `worktree_root`, validate `headRefOid`, orchestrate steps 4–5, assemble JSON, post, return `PostResult` — integration tests (mock `gh` subprocess; verify single batch call, both boundary body size cases, all fallback paths).
7. Update `commands/gate.md` to document `--comment` and the `post_findings(should_post=True)` step.
8. Update `skills/critique/SKILL.md` output step to document `--comment`.
9. Run full gate suite; confirm no regressions.

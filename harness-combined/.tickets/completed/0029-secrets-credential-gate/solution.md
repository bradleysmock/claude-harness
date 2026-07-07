# Solution

**Ticket**: 0029
**Title**: Secrets/Credential Gate

## Approach

Add `gates/secrets.py` wrapping gitleaks (preferred) with a trufflehog fallback. The gate is
injected at a single pre-dispatch insertion point in `run_suite_on_dir` so all languages get it
without per-language edits. Scanner JSON output is treated as untrusted: only structural fields
(RuleID, File, StartLine, EndLine) are extracted; line-content fields (Match, Context) are
discarded. Default is fail-closed; opt-out via `HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1`.

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `gates/secrets.py` | Scanner invocation, output parsing, GateError production | `run_secrets_gate(directory: Path) -> GateResult` (directory must be git worktree root) |
| `gates/__init__.py` | Single pre-dispatch `run_secrets_gate` call before language branching in `run_suite_on_dir` | Prepend once; all 4 languages inherit automatically |
| `tests/test_secrets_gate.py` | Unit tests | pytest with mocked `shutil.which`, subprocess, and env |
| `tests/test_secrets_gate_integration.py` | Integration tests | Fixture git worktrees with planted fake keys |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| gitleaks primary | Faster; native `.gitleaks.toml` allow-list; `--redact` suppresses raw values in JSON output |
| `gitleaks detect --source . --redact` | Native git integration → tracked files only; `--redact` removes match value from gitleaks JSON (Secret field becomes REDACTED) |
| trufflehog fallback w/ `git ls-files` pre-filter | `git ls-files` gives tracked file list; passed as explicit paths to `trufflehog filesystem` to enforce FR-7 for both backends |
| Discard Match/Context JSON fields | Only RuleID/File/StartLine/EndLine used — raw content never enters GateError or gate-findings.md |
| Redact: `rule_name @ FILE:LINE (AKIA****)` format | Locatable without exposing the credential |
| Fail-closed TOOL_MISSING | Default `passed=False`; opt-out `HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1` |
| trufflehog version detection | `trufflehog --version` output; prefix `"trufflehog 3."` → v3 parser; `"trufflehog 2."` → v2 parser; any other prefix or flag error → `passed=False` with warning (no silent parser selection) |
| Single pre-dispatch insertion in `__init__.py` | Avoids Shotgun Surgery — new languages added in future tickets inherit the gate for free |
| `Path` parameter signature | `run_secrets_gate(directory: Path)` — path semantics at the boundary; callers do `Path(str)` conversion |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1, FR-9 (gitleaks-first) | Unit | Both `which` return non-None; verify gitleaks subprocess called, trufflehog not |
| FR-2, FR-8 (suite ordering, single insertion) | Unit | `run_suite_on_dir` on fixture; `results[0].gate == "secrets"` for all 4 languages |
| FR-3 (block on finding) | Integration | Fixture git repo, planted obviously-fake key; `passed=False`, GateError has file+line |
| FR-5 (allow-list) | Integration | Same fixture + `.gitleaks.toml` allowlist; `passed=True` |
| FR-6 (blocking TOOL_MISSING) | Unit | Both absent, env unset; `passed=False`, TOOL_MISSING error |
| FR-6 (opt-out TOOL_MISSING) | Unit | Both absent, env=1; `passed=True`, warning; `gate-findings.md` written with TOOL_MISSING entry |
| FR-7 gitleaks (tracked only) | Integration | Untracked file with fake key; gate does NOT flag it (gitleaks path) |
| FR-7 trufflehog (tracked only) | Integration | Only trufflehog installed; untracked file with fake key NOT flagged |
| FR-1 trufflehog fallback | Unit | gitleaks absent, trufflehog present; correct `trufflehog filesystem` + `git ls-files` args |
| trufflehog v2 parser | Unit | Fixture v2 JSON output → correct GateError fields |
| trufflehog v3 parser | Unit | Fixture v3 JSON output → correct GateError fields |
| NFR-5 unrecognized version | Unit | `--version` returns unknown prefix; `passed=False`, warning |
| NFR-2 (redaction shape) | Unit | GateError message: (a) no raw key, (b) rule name present, (c) first 4 chars + masking |
| NFR-3 (path sanitization) | Unit | Scanner JSON with path outside worktree root → error discarded |
| FR-4 | — | xref requirements.md FR-4 |

## Tradeoffs

- **Chose discard Match/Context over masking because**: post-parse masking is fragile (regex misses variants); dropping line-content fields entirely is the only safe default.
- **Chose `git ls-files` pre-filter for trufflehog because**: trufflehog has no native --git-tracked flag; explicit file list is the only reliable way to enforce FR-7 on that path.
- **Accepting risk of**: gitleaks `--redact` removing context needed for triage — mitigated by rule name + file:line in GateError, which is enough to locate and identify the secret manually.

## Risks

- gitleaks JSON schema changes — parse defensively; unknown fields ignored; minimum tested version: gitleaks v8+.
- trufflehog v4+ with new version prefix — unrecognized prefix → fail-closed (NFR-5); no silent fallback.
- False positives in test fixtures — `.gitleaks.toml` allow-list; document the pattern.

## Implementation Order

1. `tests/test_secrets_gate.py`: write all unit tests first (TDD). FR-2 suite-ordering test mocks `run_suite_on_dir` return; will not pass real integration until step 3.
2. `gates/secrets.py`: `_detect_scanner()`, `_run_gitleaks()`, `_tracked_files()`, `_run_trufflehog()`, `_parse_gitleaks_json()`, `_parse_trufflehog_json()` (v2/v3/unknown branches), `run_secrets_gate()`
3. `gates/__init__.py`: single pre-dispatch `run_secrets_gate` call before language branching
4. `tests/test_secrets_gate_integration.py`: integration tests (step 3 required for FR-2 real path and FR-8)

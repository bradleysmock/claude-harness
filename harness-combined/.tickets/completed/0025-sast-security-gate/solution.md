# Solution

**Ticket**: 0025
**Title**: SAST Security Gate

## Approach

Add a `sast` gate phase (`gates/sast.py`) wrapping Semgrep and Bandit as a sequential phase after `tests` in `gate_run_on_dir`. Severity maps to harness vocabulary: HIGH → BLOCKER (gate fails), MEDIUM → MAJOR (warning), LOW → MINOR (warning). All file paths are project-relative. When `.semgrep.yml` is absent the `p/default` fallback emits an explicit WARNING in `gate-findings.md`. Audit existing `security` phase before registering to avoid double-Bandit. FR-7 parallelism is re-scoped to sequential — adding a concurrency layer is out of scope.

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `gates/sast.py` | Orchestrates Semgrep + Bandit; aggregates normalized findings; applies threshold; formats output | `run(worktree_dir, project_root) -> GateResult` |
| `gates/sast_semgrep.py` | Invokes Semgrep via arg list, parses JSON, normalizes to `Finding` with harness severity enum; validates config path containment | `run_semgrep(dir, config_path, project_root) -> list[Finding]` |
| `gates/sast_bandit.py` | Invokes Bandit via arg list; disambiguates exit-code-1 by JSON schema validation; normalizes to `Finding`; validates config path containment | `run_bandit(dir, config_path, project_root) -> list[Finding]` |
| `gates/sast_models.py` (new) | SAST-specific `Finding` dataclass: file (project-relative), line, rule_id, severity (enum: BLOCKER/MAJOR/MINOR), message. `Severity` enum is SAST-local; if a harness-wide vocabulary enum is later introduced, migrate here. | imported by orchestrator and tool modules |
| Gate registry | Audit existing `security` phase; register `sast` gate, replacing Bandit invocations where already present | `gate_suite.py` |

**Containment rule (both tool modules):** `config_path.resolve().is_relative_to(project_root)` must be true before passing to subprocess; if it fails, log warning and fall back to default ruleset.

**Bandit exit-code disambiguation (three-branch):** exit-code 2 → invocation error → gate failure; exit-code 1 with valid JSON containing `results` key → parse as findings; exit-code 1 with unparseable/missing-`results` JSON → invocation error → gate failure; exit-code 0 → no findings. Timeout (`subprocess.TimeoutExpired`) is a partial-results condition — emit WARNING "PARTIAL SCAN: tool timed out at 120s" and exit zero.

**All Finding file paths** are derived as `Path(raw_path).resolve().relative_to(worktree_dir.resolve())`; if this raises `ValueError` (path outside worktree), discard the finding and emit WARNING in `gate-findings.md`: "SAST tool reported a path outside worktree — skipped: {raw_path}". `project_root` = repository root (where `.semgrep.yml`/`bandit.ini` live); `worktree_dir` = scanned implementation directory — these are distinct parameters.

## Tech Choices

| Choice | Rationale |
|---|---|
| Semgrep CLI (`semgrep --json`) | Stable JSON schema; custom rulesets via `.semgrep.yml`; pattern-matching fits sub-120s budget |
| Bandit (`bandit -f json`) | Python-native; `bandit.ini` for project overrides |
| Subprocess argument lists | Required by code generation rules — no shell interpolation |
| Graceful skip when tool absent | Projects without SAST tools gate-pass with "SAST skipped" warning |
| `sast_models.py` separate from `models.py` | SAST findings have `rule_id`/`severity` fields absent from lint/typecheck models; change surfaces independently |
| Sequential (not parallel) gate position | Harness gate suite is fail-fast sequential; adding a concurrency layer is out of scope for this ticket |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|---|---|---|
| FR-1 (Semgrep with .semgrep.yml) | Unit | Config discovery returns contained `.semgrep.yml`; absent → `p/default` + WARNING in output |
| FR-2 (Bandit for Python) | Unit | Python project triggers Bandit; non-Python skips cleanly |
| FR-3 (severity classification) | Unit | HIGH→BLOCKER, MEDIUM→MAJOR, LOW→MINOR normalization |
| FR-4 (gate fails on HIGH) | Integration | Fixture triggers specific HIGH rule (e.g. `python.lang.security.audit.eval-detected`); assert rule_id and non-zero exit |
| FR-5 (gate-findings.md format) | Integration | Findings include project-relative path, line, rule_id, severity label |
| FR-6 (WARN-only = pass) | Integration | Fixture triggers MEDIUM rule by rule_id; gate passes; MAJOR warning present |
| FR-7 (no blocking of other gates) | Integration | Full gate suite on clean fixture: lint+typecheck pass, SAST phase runs last, exit zero |
| FR-8 (tool absent = skip + warn) | Unit | Mock missing Semgrep binary → exit zero, "SAST skipped" warning emitted |
| FR-9 (existing findings format) | Integration | gate-findings.md SAST section parsed by critic fixture without error |
| NFR-3 (Bandit error disambiguation) | Unit | Partial/corrupt JSON stdout + exit 1 → gate fails |
| Regression (existing gates unaffected) | Integration | Lint-clean, type-clean, no-SAST-findings fixture → gate-findings.md empty/skipped-only, exit zero |
| Containment (path traversal) | Unit | Symlinked `.semgrep.yml` outside project root → fallback to default, warning logged |

Integration tests invoke real Semgrep and Bandit binaries pinned in CI dev-dependencies. Fixtures reference specific rule IDs stable in the pinned version; version updates require re-verifying rule severity has not changed. Add unit test for truncated-JSON path (`{"results": [` incomplete → gate fails).

## Tradeoffs

- **Chose Semgrep over CodeQL:** CodeQL requires compilation; Semgrep pattern-matching fits the 120s budget.
- **Chose sequential over parallel execution:** Adding a concurrency model to the gate suite is a separate architectural change; SAST-as-last-phase is safe and avoids scope creep.
- **Chose SAST-specific models module:** Avoids coupling divergent field sets into a shared `models.py`; change surfaces independently.
- **Accepting risk of:** `p/default` rule churn causing unexpected failures — mitigated by floating-ruleset WARNING and operator guidance to pin `.semgrep.yml`.

## Risks

- Bandit exit-code-1 ambiguity: resolved by three-branch algorithm (see Components). Semgrep JSON: pin to `results[].extra.severity`, `results[].path`, `results[].start.line` (stable Semgrep v1.x).
- Timeout on large repos: `subprocess.TimeoutExpired` treated as partial-results WARNING (not gate failure); add `--max-target-bytes` to Semgrep invocation.
- Double-Bandit if existing `security` phase already runs it: **audit first** (Implementation Order step 0). Note: `post_write_gate.py` runs Bandit per-file in text mode (fast feedback); the new SAST gate runs full-directory JSON scan — complementary, not a replacement for the per-file hook.
- **Fail-fast bypass:** because `stop_full_gate.py` Python suite is fail-fast, SAST is skipped when lint/typecheck/tests fail. This is accepted as a known limitation. Operators must fix lint errors before SAST findings are surfaced. Document this in `harness-reference.md`.

## Implementation Order

0. Audit existing `security` gate phase in `post_write_gate.py` and `stop_full_gate`; document what Bandit invocations already exist and where they will be replaced.
1. Create `gates/sast_models.py` with `Finding` dataclass and `Severity` enum (BLOCKER/MAJOR/MINOR).
2. Implement `gates/sast_semgrep.py`: config discovery with containment check, subprocess invocation, JSON parse, normalization, `p/default` fallback warning.
3. Implement `gates/sast_bandit.py`: Python detection, config discovery with containment check, subprocess invocation, JSON schema validation for exit-code disambiguation, normalization.
4. Implement `gates/sast.py` orchestrator: aggregate findings from both tools, apply BLOCKER threshold, format `gate-findings.md` section, handle tool-absent skip.
5. Register `sast` gate in the gate suite, replacing existing Bandit-in-security phase where present.
6. Write unit tests (steps 1-4 surfaces: config discovery, severity mapping, containment, error disambiguation, tool-absent).
7. Write integration tests using fixture projects with known-bad patterns; pin Semgrep/Bandit versions in dev-dependencies.
8. Update `harness-reference.md` gate suite table to reflect `sast` phase replacing or consolidating `security`.

# Solution

**Ticket**: 0014
**Title**: Spec Coverage Map

## Approach

Add a `coverage.py` module to the plugin that parses `requirements.md` for FRs and ACs, parses spec `.py` files for `acceptance_criteria` using `ast.parse` (no fallback to exec-like paths), performs normalized token-overlap matching, and writes `spec-coverage.md`. The `write-spec-ticket.md` flow gains a final step that invokes `coverage.py` as a subprocess. The `build-ticket.md` flow gains an early step that reads `spec-coverage.md` and calls `coverage.py`'s `format_build_warning` function — extracting the warning text — and prints it before proceeding.

## Components

| Component | Responsibility | Key Interface |
|-----------|---------------|---------------|
| `coverage.py` | Parse requirements.md and spec files; match FRs/ACs to specs; write spec-coverage.md; emit warning text | `build_coverage_map(ticket_dir, specs_dir, project_root) -> CoverageReport`; `write_coverage_map(report, ticket_dir, project_root)`; `format_build_warning(report) -> str \| None` |
| `write-spec-ticket.md` (Step 6 addition) | After writing spec files, invoke `coverage.py` via `subprocess.run([sys.executable, "coverage.py", ticket_dir_str, specs_dir_str, project_root_str], check=True)`; report covered/uncovered counts from stdout | Argument-list subprocess; no shell interpolation |
| `build-ticket.md` (Step 1 addition) | If `spec-coverage.md` exists, invoke `coverage.py --warning-only` via `subprocess.run([sys.executable, "coverage.py", "--warning-only", ticket_dir_str, project_root_str], check=True)`; print stdout if non-empty; skip silently if file absent | `--warning-only` reads pre-written `spec-coverage.md` only — no re-parsing of spec files |
| `spec-coverage.md` template | Human-readable output artifact in ticket directory | Markdown table with columns (Requirement ID, Kind, Text, Covering Spec(s)) + Uncovered section |

## Data Types

```python
@dataclass
class Requirement:
    id: str          # "FR-1", "AC-1", etc. (position-based for ACs)
    kind: Literal["FR", "AC"]
    text: str

@dataclass
class RequirementMatch:
    requirement: Requirement
    covering_specs: list[str]   # spec IDs
    score: float                # highest Jaccard score among covering specs

@dataclass
class CoverageReport:
    covered: list[RequirementMatch]
    uncovered: list[Requirement]
    threshold: float            # Jaccard threshold used (default 0.5)
```

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Pure Python, stdlib only | No external dependencies; matches `memory.py`, `dag.py` pattern in plugin root |
| Regex-based FR/AC extraction from requirements.md | Structured format is stable; regex is readable and avoids a Markdown parser dependency |
| `ast.parse` + `ast.literal_eval` for spec file parsing; raise `SpecParseError` on failure, no fallback | Removes silent safety degradation; spec authors must use string literals in `acceptance_criteria`; parse errors surface to lead before coverage map is written |
| Jaccard token overlap at threshold 0.5 for matching | Tolerates minor wording differences; deterministic; `DEFAULT_THRESHOLD = 0.5` named constant |
| `format_build_warning` as a Python function (not inline flow doc logic) | Makes FR-5 testable: unit test calls `format_build_warning(report)` directly; flow doc invokes the subprocess |
| `--warning-only` reads pre-written `spec-coverage.md` (not re-runs matcher) | Decouples build-ticket flow from spec file availability; avoids re-parsing spec files mid-build; `specs_dir` not needed at this call site |
| Argument-list subprocess calls at both call sites | Follows CLAUDE.md hard constraint "No shell concatenation" — ticket slug or path is never interpolated into a shell string |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1 | Unit | Parse requirements.md with 3 FRs and 2 ACs; verify count, text, kind, and ID for each extracted item; parse file with non-standard header (`### Functional Requirements`) → returns empty list and emits a warning; parse file where AC section is absent → FRs extracted, ACs empty |
| FR-2 | Unit | Parse spec .py with 2 string-literal acceptance_criteria; verify extraction; parse spec with f-string criterion → `SpecParseError` raised |
| FR-3 | Unit | Exact match (score=1.0 → covered); normalized hit (case/punctuation differ, score ≥0.5 → covered); near-miss (score=0.49 → uncovered); boundary (score=0.5 → covered); unrelated pair (score near 0 → uncovered); one spec AC matching two FRs (both show as covered) |
| FR-4 | Integration | Full flow: sample requirements.md (3 FRs, 2 ACs) + 2 spec files (covering 2 FRs, 1 AC) → spec-coverage.md table present, Uncovered section lists 1 FR and 1 AC |
| FR-5 | Unit | `format_build_warning` with report containing 2 uncovered items → returns string listing both; `format_build_warning` with report containing 0 uncovered items → returns `None` |
| FR-6 | Unit | Call `write_coverage_map` twice with different reports on same ticket_dir → second call overwrites, content reflects second report; call with read-only ticket_dir → `OSError` raised (not silent) |
| Path safety | Unit | `build_coverage_map` with `ticket_dir` pointing outside `project_root` → `ValueError`; `specs_dir` outside `project_root` → `ValueError` |

## Tradeoffs

- **Chose no fallback on `ast` parse failure because**: a silent degradation is worse than an explicit error. Spec authors who need computed ACs can extract them to string constants before the `Spec(...)` call.
- **Chose subprocess invocation (not MCP tool) because**: the coverage operation reads ticket files that are local to the project, not the MCP server's domain. A subprocess is stateless and matches how the lead would invoke it manually.
- **Chose Jaccard ≥0.5 default because**: it tolerates reasonable paraphrase without accepting spurious matches; the threshold is a named constant (`DEFAULT_THRESHOLD = 0.5`) that can be changed without schema impact.
- **Accepting risk of**: false positives (a spec criterion matched to the wrong requirement). Coverage map is informational — the lead audits it.

## Risks

- Spec files with non-literal `acceptance_criteria` (f-strings, comprehensions) will raise `SpecParseError`. Mitigation: `write-spec-ticket.md` template already uses string literals; document the constraint.
- Requirements with non-standard section headers will not be parsed. Mitigation: parser logs a warning if no FRs or ACs are found after parsing.
- Subprocess invocation of `coverage.py` requires Python to be on the PATH at the path where the flow doc runs. Mitigation: use `sys.executable` in the subprocess call to ensure the same interpreter.

## Implementation Order

1. Write tests for `parse_requirements`, `parse_spec_criteria`, `match_coverage`, `write_coverage_map`, `format_build_warning`, path-safety checks (TDD — tests first)
2. `coverage.py` — `Requirement`, `RequirementMatch`, `CoverageReport` dataclasses + `SpecParseError`
3. `coverage.py` — `parse_requirements(path, project_root)` with path containment check
4. `coverage.py` — `parse_spec_criteria(spec_path, project_root)` with `ast.parse`; raise `SpecParseError` on non-literal
5. `coverage.py` — `match_coverage(requirements, spec_criteria, threshold)` with Jaccard scoring
6. `coverage.py` — `write_coverage_map(report, ticket_dir, project_root)` and `format_build_warning(report)`
7. `coverage.py` — `build_coverage_map(ticket_dir, specs_dir, project_root)` orchestrator + CLI entry point (`if __name__ == "__main__"`)
8. Update `write-spec-ticket.md` Step 6: add subprocess call to `coverage.py`; surface covered/uncovered counts
9. Update `build-ticket.md` Step 1: add subprocess call with `--warning-only`; print result if non-empty

# Requirements

**Ticket**: 0025
**Title**: SAST Security Gate

## Functional Requirements

1. The system must run Semgrep as a gate phase with a project-owned `.semgrep.yml` ruleset; if absent, fall back to the `p/default` ruleset.
2. The system must run Bandit when the project contains Python files, using `bandit.ini` if present in the project root.
3. The system must classify findings as high, medium, or low severity using the tool's native severity output.
4. The system must fail the gate when any high-severity finding is produced.
5. The system must write all findings (high, medium, low) to `gate-findings.md` with file path, line number, rule ID, severity, and a one-line description.
6. The system must write low/medium findings as warnings in `gate-findings.md` without failing the gate.
7. The system must run the SAST gate in parallel with (not blocking) the existing lint and typecheck gates.
8. The system must produce a zero-finding exit when neither tool is installed; it must emit a warning in `gate-findings.md` that SAST was skipped due to missing tooling.
9. The system must use the existing `gate-findings.md` append format so the critic and repair loop can consume SAST findings without modification.

## Non-Functional Requirements

1. The SAST gate must complete within 120 seconds for a project up to 50k LOC; findings beyond that threshold are partial and must be labelled as such.
2. Tool invocations must not use shell string interpolation; all arguments must be passed as argument lists.
3. The gate must fail closed: if Semgrep or Bandit exits with an unexpected non-zero code (not a findings-present exit), treat the run as a gate failure.

## Test Strategy

| Type        | Rationale                                                                 |
|-------------|---------------------------------------------------------------------------|
| Unit        | Parse severity classification logic, findings formatter, config discovery |
| Integration | Run gate against a fixture project containing known-bad Python/JS snippets; verify gate-findings.md content and exit code |

## Acceptance Criteria

- Gate fails (non-zero exit) when Semgrep reports a high-severity finding in a fixture file.
- Gate passes (zero exit) when only medium/low findings are present; warnings appear in gate-findings.md.
- gate-findings.md entries include file path, line number, rule ID, and severity for each finding.
- When `.semgrep.yml` is absent, Semgrep runs with `p/default` and does not error.
- When `bandit.ini` is present, Bandit picks it up; when absent, Bandit uses its default profile.
- When neither tool is installed, gate exits zero with a "SAST skipped" warning in gate-findings.md.
- Existing lint/typecheck gates are unaffected by the addition of the SAST phase.

## Open Questions

- None — all decisions derivable from the problem statement and existing harness gate conventions.

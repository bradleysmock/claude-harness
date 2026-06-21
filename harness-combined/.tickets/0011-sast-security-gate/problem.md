# Problem Statement

**Ticket**: 0011
**Title**: SAST Security Gate
**Date**: 2026-06-21

## Problem

The harness gate pipeline covers syntax, type, and lint checks but has no automated static analysis security testing (SAST) phase. Security vulnerabilities in delivered code are only caught by manual review or post-deployment, making the harness's quality guarantee incomplete for security-sensitive projects.

## Impact

- Harness operators ship code with undetected security defects (hardcoded secrets, injection sinks, weak crypto) that automated tooling would have caught.
- Without a project-owned ruleset, teams cannot express custom security policies through the pipeline.
- High-severity findings are treated identically to low-severity ones — there is no severity-based gate to block delivery.

## Success Criteria

- A SAST gate phase runs alongside lint and typecheck during the gate pipeline.
- Semgrep runs with a project-owned `.semgrep.yml` ruleset (falls back to a default ruleset if absent).
- Bandit runs for Python projects using `bandit.ini` if present in the project root.
- High-severity findings cause the gate to fail and are written to `gate-findings.md` with file and line references.
- Low/medium-severity findings are written to `gate-findings.md` as warnings and do not block delivery.
- Gate findings are surfaced in the existing `gate-findings.md` format consumed by the critic and repair loop.

## Out of Scope

- Dynamic analysis (DAST) or runtime scanning.
- Automatic remediation of findings — findings are reported only.
- Integration with external SAST platforms (SonarQube server, Semgrep Cloud App).
- License compliance scanning.

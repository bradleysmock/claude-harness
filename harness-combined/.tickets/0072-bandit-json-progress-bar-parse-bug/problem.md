# Problem Statement

**Ticket**: 0072
**Title**: Security gate silently swallows bandit findings when bandit's stdout progress bar breaks JSON parsing
**Date**: 2026-07-20

## Problem

`gates/python.py::_security_gate_dir` runs `bandit -r . -f json ...` and feeds
`result.stdout` straight to `_parse_bandit_json`. bandit 1.9.4 (and possibly
earlier 1.9.x releases) prints a `Working... [progress bar] 100% 0:00:01` line
to stdout *before* the JSON payload. `_parse_bandit_json` fails to parse this
(JSON starts mid-stream, not at column 1) and silently returns an empty error
list — discovered while provisioning bandit for the first time in this
environment (it was previously uninstalled, so this code path never ran) as
part of ticket 0071's build.

The gate still reports `passed=False` (bandit's own exit code is 1 because it
found real medium+ severity issues), but with `errors=[]` — so the gate fails
opaquely: no `file:line` findings surface anywhere, telling the lead nothing
about what to fix, and repair loops have nothing to act on.

## Impact

Any project where bandit is actually installed and finds real issues gets an
unactionable, opaque security-gate failure — the gate can never turn green by
fixing findings because none are shown, only by findings dropping below the
severity threshold or via a config change. Effectively blocks the `security`
gate for any codebase with real bandit output on affected bandit versions.

## Success Criteria

- `_parse_bandit_json` (or its caller) tolerates a leading non-JSON progress
  line and still extracts the real findings.
- A forced/mocked bandit stdout containing the progress-bar prefix parses
  identically to the same output without it.
- No behavior change for bandit versions that already emit clean JSON.

## Out of Scope

- Ticket 0071 (deliver's remote-branch cleanup) — unrelated; this was
  discovered as a side effect of provisioning bandit in the build environment.
- The gitleaks fixture flake tracked separately in
  `tests/test_0029_secrets_gate_integration.py::test_planted_key_blocked_gitleaks`.

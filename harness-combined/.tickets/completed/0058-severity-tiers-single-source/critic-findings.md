## Round 1 — 2026-07-19

# Critic Report — Ticket 0058-severity-tiers-single-source

**Phase:** code · **Round:** 1

**Active panels:** Core (always active) + Python (`tests/test_0058_severity_single_source.py` matches `**/*.py`) + Testing (`tests/**` glob). No other panel triggers fire — the remaining three files are prose docs, and the ticket does not touch HTTP/API, security-library, or UI surfaces beyond the plain-text severity taxonomy.

## Step 2.5 — Ticket-baseline checks

- **Requirements coverage**: FR-1 through FR-8 and NFR-1/NFR-2 each have a corresponding implementation and test. Verified by direct inspection: `context/harness-reference.md:388-395` (canonical block, phase-neutral wording, no "deliver summary" token, "checkpoint" present in BLOCKER), `context/critic-brief.md:75` and `skills/critique/SKILL.md:75,179` (heading-named pointers with "read that section before producing findings"), and `tests/test_0058_severity_single_source.py` (20 tests, fail-closed scan, parser pin). No gaps found.
- **Solution alignment**: matches `solution.md`'s Components/Tech Choices — matcher lives in the test module (no new production surface), paths anchored to `Path(__file__).parent.parent`, parser pin imports `gates.critic_finding_parser`. No unjustified deviations.
- **Weakened/deleted tests**: N/A — this is a new test file; no prior tests were touched.

## Verification performed

Manually re-derived what the drift scan should find by grepping the whole worktree for `**BLOCKER**` / tier mentions across all scanned roots (`context/`, `commands/`, `skills/`, `agents/`, `README.md`, `CLAUDE.md`). Confirmed by hand that:
- The only 4-tier co-located block is `context/harness-reference.md:392-395`.
- Every other `BLOCKER`/`MAJOR`/`MINOR`/`OBS` occurrence in scanned files (`context/critic-brief.md:53-55`, `skills/critique/SKILL.md:112-259`, `context/panels/cryptography.md:97`, `context/panels/uswds.md:43`, `context/flows/build-ticket.md:260`, `skills/review/SKILL.md:53`, `context/harness-reference.md:239-240,376,385,399-400,429`) is either a non-bulleted paragraph, an unbolded table cell, or a bold span extending past the tier name — none satisfy the `_TIER_LINE_RE` grammar, consistent with the FR-8 negative fixtures.
- `_scan_files`'s fail-closed error strings (`"scan root missing: …"`, `"…contributed zero markdown files: …"`, `"harness-reference.md absent…"`, `"pointer-named heading … missing…"`) match exactly what the four FR-6 tests assert via `pytest.raises(..., match=...)`.
- `conftest.py:8` puts the repo root on `sys.path`, so `from gates.critic_finding_parser import _SEVERITIES` (`tests/test_0058_severity_single_source.py:27`) resolves correctly under `--import-mode=importlib`.

## Findings

No BLOCKER, MAJOR, or MINOR findings.

- **OBS** · Testing / Dimension 22 (Test Strategy & Suite Shape) · `tests/test_0058_severity_single_source.py:191-278` — `test_fr4_injected_copy_in_tmp_clone_fails` and the four `test_fr6_*` tests each independently `shutil.copytree` the full `context/`, `commands/`, `skills/`, `agents/` trees into a fresh temp dir (five full-tree copies across the suite) rather than sharing one clone via a fixture. At current repo size this is fast enough not to matter, but it's the kind of duplication that becomes a "slow CI suite" hazard if the scanned trees grow. A session-scoped fixture producing one base clone that each test copies/mutates would remove the redundancy. Logged only — not worth blocking on.
- **OBS** · Core / Dimension 7 (Test Quality) · `tests/test_0058_severity_single_source.py:284-287` — `test_fr7_canonical_tier_names_match_parser_severities` only exercises the "equal" case; the acceptance criterion "the parser-pin assertion fails if a tier is renamed in only one of prose or `_SEVERITIES`" is satisfied by construction (a plain `==`/`set()` comparison, and the regex's hardcoded tier alternation) rather than by a dedicated fixture proving the failure mode, unlike FR-6's explicit `pytest.raises` fixtures. Given the assertion is a one-line equality check, a dedicated regression fixture would be low-value, but it's worth noting the asymmetry with FR-6's more rigorous fail-closed proof style.

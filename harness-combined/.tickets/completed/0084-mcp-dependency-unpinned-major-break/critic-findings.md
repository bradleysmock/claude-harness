# Critic Findings — 0084-mcp-dependency-unpinned-major-break

## Round 1 — 2026-09-17

**Panels active**: Core; Python; Shell; Testing. Candidates deferred: `cicd`, `observability`, `ai-llm`. Skipped: the critic could not execute `panel_detect.py` (read-only toolset) and derived activation by hand from `context/panels/triggers.md`.

**Gate findings consulted**: `gate-findings.md` records only a skipped Coverage section; nothing re-flagged.

No BLOCKER findings. Requirements coverage: FR-1, FR-3, FR-4 each have an implementation and a test that runs by default; FR-2's implementation is present and its dedicated test exists but never runs by default (judged below).

**MAJOR** · Core / Dimension 7 + Testing / Dimension 22 · `tests/test_0084_mcp_requirements_pin.py:105` <!-- harness-finding-key tests/test_0084_mcp_requirements_pin.py:105:MAJOR:Core / Dimension 7 + Testing / Dimension 22 -->

The FR-4 baseline test is a guaranteed time bomb, not an environment-conditional skip. `/deliver` merges with `git merge --squash` and drops the branch, so `approved-commit: 4952652…` will not be an ancestor of `main`; on any fresh clone the `cat-file -e` probe at line 105 fails immediately and `pytest.skip` at line 131 fires forever. What lands on `main` is ~70 lines of git plumbing whose only assertion can never execute again, and nothing in the suite reports that the coverage evaporated. The repo's other `skipif` guards skip on *absent toolchains*, a condition that can be satisfied — this one cannot. Either delete the test (FR-4 is a diff-scoped constraint verified at review time and implied by the FR-1 assertions) or replace the git reconstruction with a durable, self-contained assertion.

**MINOR** · Core / Dimension 4 · `README.md:57` <!-- harness-finding-key README.md:57:MINOR:Core / Dimension 4 -->

The change made the venv self-heal condition stricter, and the user-facing description of it is now the wording of the old, defective check: "it rebuilds if deleted or if `mcp` stops importing" is exactly the bare-package semantics that let a 2.x venv pass. Replace it with the real condition.

**MINOR** · Testing / Dimension 22 · `tests/test_0084_harness_server_health_check.py:230` <!-- harness-finding-key tests/test_0084_harness_server_health_check.py:230:MINOR:Testing / Dimension 22 -->

`HARNESS_TEST_NETWORK` appears nowhere in the repository outside this module's docstring and this `skipif` — no README entry, no `harness-reference.md` entry, no scheduled job. The gating tradeoff itself is sound; what makes it a gap in practice is that the switch is undiscoverable. Document it next to `HARNESS_PYTHON` in the README.

**MINOR** · Core / Dimension 5 · `tests/test_0084_harness_server_health_check.py:66` <!-- harness-finding-key tests/test_0084_harness_server_health_check.py:66:MINOR:Core / Dimension 5 -->

`test_ac2_health_check_no_longer_probes_the_bare_package` cannot fail while `test_fr3_health_check_probes_the_submodule_import` passes: line 61 already asserts the probe list equals `[REQUIRED_IMPORT]` exactly, so the membership check is subsumed. It is also weaker than its docstring implies — list membership is exact string equality per probe, so `import mcp; import sys` would satisfy it.

**MINOR** · Python / Dimension 10 · `tests/test_0084_harness_server_health_check.py:261` <!-- harness-finding-key tests/test_0084_harness_server_health_check.py:261:MINOR:Python / Dimension 10 -->

The `TimeoutExpired` branch is unreachable in practice and carries a version-dependent type assumption. `_launch` passes `stdin=subprocess.DEVNULL`, so the real stdio server sees EOF and exits rather than blocking. If it ever were reached, `(expired.stderr or b"").decode(...)` assumes bytes: CPython's POSIX path attaches raw byte chunks, but the Windows path re-runs `communicate()` after `kill()` and hands back decoded `str` under `text=True`, where `.decode` raises `AttributeError`.

**MINOR** · Core / Dimension 5 · `tests/test_0084_harness_server_health_check.py:87` <!-- harness-finding-key tests/test_0084_harness_server_health_check.py:87:MINOR:Core / Dimension 5 -->

`_site_packages` carries a Windows fallback (`venv.glob("Lib/site-packages")`) that no caller can reach: every path through these tests runs a bash script and hardcodes `.venv/bin/python`, both POSIX-only. Speculative generality.

**OBS** · Shell / Dimension 29 · `bin/harness-server:43` <!-- harness-finding-key bin/harness-server:43:OBS:Shell / Dimension 29 -->

The repair path has no verification. If `pip install -r requirements.txt` exits 0 but the venv still cannot satisfy the probe, the launcher `exec`s `server.py` anyway and the failure resurfaces as `CONNECTION_CLOSED` with no stderr diagnostic. Logged as OBS because `solution.md` and NFR-1 explicitly scoped a second check out; a follow-up ticket may be the right home.

**OBS** · Testing / Dimension 22 · `tests/test_0084_harness_server_health_check.py:204` <!-- harness-finding-key tests/test_0084_harness_server_health_check.py:204:OBS:Testing / Dimension 22 -->

In the hermetic AC-4 test the "server starts clean afterward" half is true by construction: the stub pip fabricates `mcp/server/fastmcp.py` itself. The load-bearing assertions are the two above it (`pip_log.is_file()` and `"install -r" in …`), which are real evidence that the corrected probe triggers a bootstrap.

**OBS** · Core / Dimension 1 · `bin/harness-server:35` <!-- harness-finding-key bin/harness-server:35:OBS:Core / Dimension 1 -->

Every launch now pays a full `mcp.server.fastmcp` import (pydantic and the FastMCP stack) in a throwaway interpreter before `exec`, where the old probe loaded only the top-level package. The accuracy is worth the cost, but launcher latency is on the path of every session start, so the regression is real and unmeasured.

Solution alignment: the implementation matches `solution.md`'s Components table exactly, including the Risks-section mitigation. No deviation to report. No test was weakened or deleted relative to the Test Plan; both planned test tiers exist.

## Round 2 — 2026-09-17

**Panels active**: Core; Python; Testing. Candidates deferred: `cicd`, `ai-llm`, `observability`, `performance`, `distributed`. The critic could not execute `panel_detect.py` (read-only toolset) and derived activation from `context/panels/triggers.md` directly.

**Pass 1 — prior-finding classification.** The round-1 MAJOR at `tests/test_0084_mcp_requirements_pin.py:105` is **FIXED**: the git-reconstruction apparatus (`_run_git`, `_ticket_status_path`, `_approved_commit`, `_baseline_requirements`, `_with_pin_applied`) and the skipping test are gone; all three remaining tests run unconditionally with no `skipif` and no `pytest.skip`. Not re-emitted.

**Pass 2 — new findings.**

**MINOR** · Python / Dimension 10 · `tests/test_0084_mcp_requirements_pin.py:39` <!-- harness-finding-key tests/test_0084_mcp_requirements_pin.py:39:MINOR:Python / Dimension 10 -->

The file hand-rolls three parses of requirement syntax — `_DISTRIBUTION_RE` for the name, `.lower()` for normalization, `.removeprefix("mcp")` for the specifier — while already importing `packaging`, whose `packaging.requirements.Requirement` yields `.name` and `.specifier` and whose `packaging.utils.canonicalize_name` implements PEP 503 normalization. The hand-rolled version is weaker in three ways: `.lower()` is not canonicalization, so `types-PyYAML` and `types_pyyaml` read as distinct distributions and the duplicate-pin test would miss that duplicate; `removeprefix("mcp")` on a line carrying an extra (`mcp[cli]>=1.0,<2.0`) leaves `[cli]>=1.0,<2.0` and raises `InvalidSpecifier` rather than asserting; and the regex accepts trailing garbage that `Requirement` rejects. That last point bears on the dropped mangle test: `Requirement("mcp>=1.0,<2.0 # Gate tooling — …")` raises `InvalidRequirement`, so the stronger primitive catches exactly the case that made the regex version near-vacuous. Fix shape: replace `_DISTRIBUTION_RE`/`_distribution_of` with a `Requirement(line)` parse plus `canonicalize_name(parsed.name)`, derive the FR-1 specifier from `.specifier`, and let the parse itself stand as the neighbour-integrity assertion. Caveat to encode deliberately: pip permits inline ` # comment`, which `Requirement` rejects — do not strip inline comments before parsing (that reintroduces the vacuity); note in the docstring that the assertion also pins the file's house style of comments on their own lines.

**MINOR** · Core / Dimension 6 · `tests/test_0084_mcp_requirements_pin.py:28` <!-- harness-finding-key tests/test_0084_mcp_requirements_pin.py:28:MINOR:Core / Dimension 6 -->

`from packaging.specifiers import SpecifierSet` relies on `packaging` being a transitive dependency of `pytest` rather than a declared one. Acceptable in practice, but inconsistent with this repo's own convention: `requirements.txt` declares `sarif-tools>=1.0` with a four-line comment marking it dev/test-only for exactly this situation, and declares `types-PyYAML` purely to satisfy a type-check path. A ticket whose thesis is that an under-specified dependency constraint breaks a fresh bootstrap should not introduce a test depending on an undeclared transitive. The failure mode is loud (collection-time `ImportError` fails the pytest gate), which is why this is MINOR. Fix: add `packaging>=23.0` to `requirements.txt` with a comment naming this test as the consumer. Adding a line does not violate FR-4, which constrains existing lines.

**MINOR** · Core / Dimension 3 · `tests/test_0084_mcp_requirements_pin.py:94` <!-- harness-finding-key tests/test_0084_mcp_requirements_pin.py:94:MINOR:Core / Dimension 3 -->

`named = Counter(...)` names the variable after an adjective, not what it holds: a count of requirement lines per canonical distribution name. `pins_per_distribution` or `lines_per_distribution` states it.

**OBS** · Testing / Dimension 22 · `tests/test_0084_mcp_requirements_pin.py:69` <!-- harness-finding-key tests/test_0084_mcp_requirements_pin.py:69:OBS:Testing / Dimension 22 -->

`test_fr1_pin_admits_one_x_and_excludes_two_x` cannot fail unless `test_fr1_mcp_pin_excludes_the_two_x_release_line` has already failed: the first asserts the requirement line equals the frozen literal, the second parses that same literal. Every alternative spelling its docstring names (`<2`, `!=2.*`) is already excluded by the string equality, so it contributes no independent failure mode — its value is as executable documentation of why the ceiling is spelled this way. Defensible, and FR-1/AC-1 do mandate the exact string. If the lead wants independent failure modes, relax the first to "exactly one `mcp` requirement line exists" and let the second carry the version semantics.

**OBS** · Core / Dimension 4 · `tests/test_0084_mcp_requirements_pin.py:9` <!-- harness-finding-key tests/test_0084_mcp_requirements_pin.py:9:OBS:Core / Dimension 4 -->

Rating the FR-4 coverage gap: acceptable as documented, OBS not BLOCKER. The weakened-tests check does bite — `solution.md`'s Test Plan promises "every other line is byte-identical to the pre-change file" and no test now asserts that — but this is not the balanced-swap pattern the check exists to catch: the deletion was directed by round 1's MAJOR against an assertion that could never execute again post-squash, and the swap traded one permanently-skipping test for two unconditionally-running ones. The docstring states the split and its reasoning plainly, which is the right way to leave a deliberate gap. Two residual notes: `solution.md`'s Test Plan row still reads as though the byte-identical assertion exists; and the gap narrows if the `Requirement`-parse finding above is taken.

**Summary**: no BLOCKER or MAJOR findings this round. The prior MAJOR is fixed.

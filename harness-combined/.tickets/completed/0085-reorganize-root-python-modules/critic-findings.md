# Critic findings

## Round 1 — 2026-09-18

**MAJOR** · Core / Dimension 4 · `commands/flaky.md:21` <!-- harness-finding-key commands/flaky.md:21:MAJOR: -->

Fourteen LLM-facing call directions still name a moved module by its bare top-level name, in files containing no import statement and no `${CLAUDE_PLUGIN_ROOT}` path, so `import flaky_detect` / `import audit` / `import ticket_templates` now raises ModuleNotFoundError. Sites: commands/flaky.md:21,22; commands/gate.md:21; commands/abandon.md:21; commands/cancel.md:43; commands/reopen.md:39; commands/ticket-status.md:6; context/flows/autopilot-ticket.md:85; commands/problem.md:61,62,65,69,73,76,79.

**MAJOR** · Core / Dimension 4 · `harness-pi/prompts/problem.md:47` <!-- harness-finding-key harness-pi/prompts/problem.md:47:MAJOR: -->

Four live invocation strings in the tracked sibling consumer harness-pi/ still exec the pre-move absolute path (problem.md:47, abandon.md:24, cancel.md:47,50). convert-commands.mjs expands `${CLAUDE_PLUGIN_ROOT}` at convert time, so neither the pattern sweep nor the new test could see them. problem.md:292 and ticket-status.md:65 also still read `from ticket_deps import`.

**MAJOR** · Core / Dimension 4 · `skills/health/SKILL.md:20` <!-- harness-finding-key skills/health/SKILL.md:20:MAJOR: -->

The /health skill's only invocation instruction is a bare `python3 health.py .`, which fails from any cwd now that the module is lib/health.py. Its doc guard tests/test_0016_health_docs.py:34 asserts the substring `health.py`, which reads identically before and after the move.

**MAJOR** · Core / Dimension 4 · `docs/design/00-overview.md:107` <!-- harness-finding-key docs/design/00-overview.md:107:MAJOR: -->

The plugin's design-of-record still describes the pre-move layout as fact: the directory map enumerates all 18 modules as flat children of harness-combined/ with no lib/ entry, and docs/design/03-mcp-server.md:74 heads its section 'Supporting root modules' with a `python3 ticket.py set-status` CLI example at line 78.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:79` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:79:MINOR: -->

_tracked_files() runs git ls-files with cwd=ROOT (the plugin root), so the sweep enumerates only harness-combined/ while the docstring and AC-3 both claim repo-wide scope. This is the blind spot that let the harness-pi references survive.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:150` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:150:MINOR: -->

The sweep asserts only the absence of the old path; nothing asserts that each `${CLAUDE_PLUGIN_ROOT}/....py` reference resolves to a file that exists. A mistyped new segment (lib/tickets.py, libs/ticket.py) passes all 28 tests while breaking the flow exactly as a missed old path would.

**MINOR** · Python / Dimension 10 · `lib/autopilot_watch.py:31` <!-- harness-finding-key lib/autopilot_watch.py:31:MINOR: -->

sys.path.insert executes at import time in a library module with `from lib import ticket` deferred behind a noqa: E402. The mutation exists only because the bash launchers exec these files as scripts — a property of the launcher, not the module. Suggested: PYTHONPATH="$ROOT" exec python3 -m lib.autopilot_watch, which removes both modules' inserts and both suppressions.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:145` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:145:MINOR: -->

test_server_puts_the_plugin_root_on_sys_path_not_its_own_directory asserts an exact source substring, pinning the mechanism rather than the outcome. It fails on any correct refactor and passes if the literal appears in a comment. Already covered by the fresh-interpreter import and MCP-tool-registry tests.

**MINOR** · Core / Dimension 4 · `lib/ticket.py:1` <!-- harness-finding-key lib/ticket.py:1:MINOR: -->

Three moved modules retain a first-line comment naming their pre-move location (lib/ticket.py:1, lib/learnings.py:1, lib/spec_coverage.py:1). Two hook comments drifted the same way: hooks/stop_full_gate.py:276's worked example and line 57's reference to the `models` package.

**MINOR** · Core / Dimension 4 · `context/flows/write-spec-ticket.md:91` <!-- harness-finding-key context/flows/write-spec-ticket.md:91:MINOR: -->

The two spec_coverage.py subprocess sites became cwd-relative `lib/spec_coverage.py`, the only Python invocations in the corpus not using `${CLAUDE_PLUGIN_ROOT}/lib/<module>.py`. Faithful to the pre-move form, but line 98 defines project_root_str as the plugin root in the same paragraph, conflating two directories.

**OBS** · Core / Dimension 3 · `lib/__init__.py:1` <!-- harness-finding-key lib/__init__.py:1:OBS: -->

`lib` is the one directory at the plugin root naming no concern, unlike gates/, hooks/, validators/, skills/, commands/, context/, bin/. Logged only: requirements delegated the name to Solution, solution.md chose it with a stated rationale, and the lead approved it at Checkpoint 1.

**OBS** · Core / Dimension 4 · `.tickets/0085-reorganize-root-python-modules/solution.md:15` <!-- harness-finding-key .tickets/0085-reorganize-root-python-modules/solution.md:15:OBS: -->

Two documented deviations, both benign. (a) solution.md promises server.py's sys.path insert is unchanged; it had to become .parent.parent to keep resolving the same directory. (b) FR-1 and solution.md say '17 modules' while enumerating 18; the build treated the enumeration and AC-1 as authoritative.

**OBS** · Core / Dimension 4 · `docs/superpowers/plans/2026-06-23-multidev-ticketing.md:717` <!-- harness-finding-key docs/superpowers/plans/2026-06-23-multidev-ticketing.md:717:OBS: -->

The build's exclusion of this repo-root plan document holds up on inspection (4 token hits plus 9 prose hits; a dated record of what was proposed, read by no flow). Noted only that FR-3's literal wording does not grant the exclusion, so either the requirement or the exclusion list should be amended before archiving.

**Verdict**: no BLOCKER. FR-1, FR-2, FR-4, FR-5, FR-6 implemented and tested; FR-3
substantially met, with four live-reference classes the `${CLAUDE_PLUGIN_ROOT}`-shaped
pattern could not see.

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 4 |
| MINOR | 6 |
| OBS | 3 |

## Round 2 — 2026-09-18

Incremental round. All four round-1 MAJORs verified FIXED at their stated
locations; three new MAJORs, all inside round 1's own repair blast radius.

**MAJOR** · Core / Dimension 4 · `context/flows/autopilot-ticket.md:81` <!-- harness-finding-key context/flows/autopilot-ticket.md:81:MAJOR: -->

The audit -> lib.audit requalification was applied as a blind text replacement and corrupted three sites where `audit` was English prose or a third-party name: this line read 'the /refine lib.audit trail'; commands/gate.md:47 named the Rust tool `cargo-lib.audit`; commands/ticket-status.md:103 listed 'lib.audit foundation' as a /sprint wave-label example the model copies verbatim. solution.md:48 anticipated exactly this and prescribed reviewing every match before committing; the mitigation was not performed.

**MAJOR** · Core / Dimension 4 · `commands/gate.md:70` <!-- harness-finding-key commands/gate.md:70:MAJOR: -->

Round 1 missed a call site in a file it edited: `sarif_output.sarif_optin_enabled(project_root)` is a bare top-level module name in a file with no `from lib import sarif_output`, 49 lines below the call the same round qualified at line 21.

**MAJOR** · Core / Dimension 4 · `harness-pi/prompts/problem.md:69` <!-- harness-finding-key harness-pi/prompts/problem.md:69:MAJOR: -->

The generated pi prompt tree was hand-patched for path strings and imports but not for round 1's call-qualification fix, so the derived tree contradicts its generator's input. Eleven bare call directions remained (problem.md:69,76,80,88,98,100,105; gate.md:24,62; flaky.md:24,25), plus harness-pi/prompts/health.md:6 still reading the pre-fix health prose. Neither sweep can see any of these.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:179` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:179:MINOR: -->

Both sweeps anchor on a path prefix, so a reference naming a moved module with no path at all is invisible to the guard — precisely the class that produced round 1's MAJOR 1 and MAJOR 3. A third sweep over the call-direction shape would have caught gate.md:70 mechanically.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:32` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:32:MINOR: -->

Two failure modes in the new root resolution: (a) subprocess check=True at module scope makes the file a collection error, not a skip, wherever the plugin tree is not inside a git checkout (the /plugin install cache, any sdist extraction); (b) when the plugin is the repo root, relative_to yields '.', so PLUGIN_PREFIX == '.' and five guards pass vacuously green.

**MINOR** · Core / Dimension 4 · `commands/problem.md:57` <!-- harness-finding-key commands/problem.md:57:MINOR: -->

Bare module-file prose references now sit beside qualified call directions in the same paragraph (line 57 'the pure helper module `ticket_templates.py`', line 82 'See each function's docstring in `ticket_templates.py`'). Same pattern at harness-pi/prompts/{ticket-status.md:61,problem.md:64,287,build.md:10} and tests/test_0016_health_docs.py:5. Each is now a wrong relative path and invisible to both sweeps. One MINOR for the class — the lead may prefer short-form module names in prose, but should say so once rather than per file.

**OBS** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:176` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:176:OBS: -->

The plugin-scoping rationale is correct in principle but not load-bearing in this tree: no file under harness-no-api-key/ or harness-full/ currently carries a `${CLAUDE_PLUGIN_ROOT}/<module>.py` token for any of the 18 names, so removing the filter would change no outcome today. The docstring states the hazard in present tense.

**OBS** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:98` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:98:OBS: -->

_tracked_files() is called by five tests and is uncached: each call re-runs git ls-files over the whole repo, and two sweeps then read the full text of every tracked file. A module-level functools.cache on _tracked_files and _text_of costs one line each.

**OBS** · Core / Dimension 4 · `docs/design/00-overview.md:113` <!-- harness-finding-key docs/design/00-overview.md:113:OBS: -->

The new lib/ subtree's glyphs are slightly off: the block's last child uses a tee where an elbow belongs, and the two continuation lines begin with a doubled vertical, rendering as children of the preceding entry. Cosmetic; content is correct and complete.

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 3 |
| MINOR | 3 |
| OBS | 3 |
| Round 1 MAJORs persisting | 0 |

## Round 3 — 2026-09-18

Incremental round. All three round-2 MAJORs verified FIXED. No BLOCKER, no MAJOR.
The critic independently confirmed the new call-shape guard would have caught all
three historical instances of the recurring class.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:304` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:304:MINOR: -->

The new sweep's exemption is file-scoped, not site-scoped: one legitimate `from lib import audit` anywhere grants every other bare call of that module in the file a permanent pass. Four files are now wholly exempt for `audit`, including the two longest flows in the corpus. This is the same shape as round 2's MAJOR 2 (a bare call surviving 49 lines below a qualified one), so the guard built to prevent that recurrence cannot see it inside those four files. Scope the exemption to the enclosing fenced block, or require the import to precede the call's offset.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:297` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:297:MINOR: -->

The new sweep carries no non-vacuity assertion, unlike the repo-wide sweep which gained two. The `harness-pi/prompts/` quarter is a hardcoded repo-root literal with no plugin-relative derivation, so removing or renaming that sibling silently drops it while `offenders == {}` still passes.

**MINOR** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:203` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:203:MINOR: -->

`assert PLUGIN_PREFIX` fixes round 2's vacuity by converting a legitimate layout into a red test: when the plugin is the repo root this reports the code as broken rather than the check as inapplicable. `pytest.skip` states the same fact without a false failure. Same shape as round 2's un-repaired MINOR (a), so the lead may want one policy for 'this guard cannot run in this layout'.

**MINOR** · Core / Dimension 4 · `harness-pi/prompts/health.md:6` <!-- harness-finding-key harness-pi/prompts/health.md:6:MINOR: -->

Mirroring commands/health.md verbatim carried the raw `${CLAUDE_PLUGIN_ROOT}` token into the generated tree — now the only occurrence under harness-pi/prompts/, where the six other references carry the expanded absolute path. convert-commands.mjs:7-9 states pi cannot resolve that token. Pre-dates this round (the repair only inserted `lib/`, strictly improving the line); mirroring the converter's output form would have matched its siblings.

**OBS** · Testing / Dimension 22 · `tests/test_0085_lib_package_layout.py:290` <!-- harness-finding-key tests/test_0085_lib_package_layout.py:290:OBS: -->

`[a-z_]+` as the member-name class excludes capitalized or digit-bearing attributes, so `models.Ticket(...)` would be invisible. No such site exists today; `[A-Za-z_]\w*` would close it at no false-positive risk, since the `\(` and the lookbehind carry the precision.

**OBS** · Core / Dimension 4 · `context/flows/build-ticket.md:276` <!-- harness-finding-key context/flows/build-ticket.md:276:OBS: -->

Two conventions for the same call now coexist: four files pair `from lib import audit` with a bare `audit.record(...)`, while the 27 requalified sites use fully-qualified `lib.audit.record(...)` with no import. Both work; the split is a consequence of the repair skipping already-imported sites rather than a decision. Worth one sentence in docs/design/ if the lead wants one form canonical, since the guard's exemption rule now encodes the distinction.

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 0 |
| MINOR | 4 |
| OBS | 2 |
| Round 2 MAJORs persisting | 0 |

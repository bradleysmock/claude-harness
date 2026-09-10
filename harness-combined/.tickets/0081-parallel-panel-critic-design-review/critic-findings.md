# Critic Findings

## Round 1 — 2026-09-10

Panels active: Core, Python, Testing, AI/LLM

**BLOCKER** · Core / Dimension 4 · `context/critic-brief.md:31` <!-- harness-finding-key context/critic-brief.md:31:BLOCKER:Core / Dimension 4 -->

Step 1 carries two contradictory rules about Core for a fanned-out specialist agent. Lines 13 and 31 state Core is always active, unqualified; the new `Panels:` block says to treat the named panels as the fixed and complete set. A `Panels: Python` agent that resolves Core as active announces `Panels active: Core, Python`, which Phase 5's exact-match check rejects, halting the round on a correctly-behaving agent.

**BLOCKER** · Core / Dimension 8 / McGraw · `commands/problem.md:362` <!-- harness-finding-key commands/problem.md:362:BLOCKER:Core / Dimension 8 / McGraw -->

Branch A skips the per-agent verification, dropping FR-7's presence check on the path most design reviews take. An errored or empty subagent response flows into revision as if it were a clean review.

**MAJOR** · AI/LLM / Dimension 15 / Willison · `commands/problem.md:375` <!-- harness-finding-key commands/problem.md:375:MAJOR:AI/LLM / Dimension 15 / Willison -->

The panel-scope check verifies a self-declared header, not the findings. A specialist emitting `Panels active: Python` plus a `Core / Dimension 8` finding header passes the check and the out-of-partition finding is merged.

**MAJOR** · AI/LLM / Dimension 15 / Willison · `commands/problem.md:379` <!-- harness-finding-key commands/problem.md:375:MAJOR:AI/LLM / Dimension 15 / Willison -->

The halt-and-retry path is unbounded and unowned: no maximum attempt count, no statement of whether Phase 5 re-spawns itself or waits for the lead.

**MAJOR** · Core / Dimension 4 · `context/harness-reference.md:603` <!-- harness-finding-key context/harness-reference.md:603:MAJOR:Core / Dimension 4 -->

The canonical operational reference now makes a false claim: "every panel loads against the full file set". Under Branch B each agent loads exactly one panel. Lines 526 and 530 drift the same way.

**MAJOR** · Testing / Dimension 7 · `tests/test_0081_problem_phase5_fanout.py:58` <!-- harness-finding-key tests/test_0081_problem_phase5_fanout.py:58:MAJOR:Testing / Dimension 7 -->

Tautological assertions: line 58's `"every" in lowered and "agent" in lowered`, line 65's `"one" in lowered`, and line 136's `"once" in lowered` pass on the pre-change text, leaving FR-2, FR-3, and FR-8's header requirement effectively untested.

**MINOR** · Core / Dimension 4 · `agents/critic.md:11` <!-- harness-finding-key agents/critic.md:11:MINOR:Core / Dimension 4 -->

The critic subagent's field enumeration (Phase, Ticket, Round) was not updated for `Panels:`.

**MINOR** · Core / Dimension 9 / Evans · `commands/problem.md:319` <!-- harness-finding-key commands/problem.md:319:MINOR:Core / Dimension 9 / Evans -->

In `--design` mode `panel_detect.py` evaluates only manifests and deps, so the inferred file list contributes nothing to `active` while every inferred-but-absent path lands in `skipped`. `N` is decided almost entirely by root-manifest presence, and the candidate enumeration is large on every round.

**OBS** · Core / Dimension 4 · `agents/critic.md:4` <!-- harness-finding-key agents/critic.md:4:OBS:Core / Dimension 4 -->

The critic declares `tools: Read, Grep, Glob`, so it cannot execute `panel_detect.py`; the no-`Panels:` self-detection path is unexecutable as written. Pre-existing; argues for extending `Panels:` to `build-ticket.md` Step 7.

**OBS** · Core / Dimension 4 · `context/critic-brief.md:114` <!-- harness-finding-key context/critic-brief.md:114:OBS:Core / Dimension 4 -->

Pre-existing: the bullet says the location token is "first on the line" while the pinned template places it third.

## Round 2 — 2026-09-10

Panels active: Core, Python, Testing, AI/LLM

Pass 1 — prior-finding classification: all six prior BLOCKER/MAJOR findings **fixed**, verified by reading the current text at each location. Weakened/deleted-tests check against solution.md's Test Plan: no test removed, skipped, or suppressed; every Test Plan row still has a covering test; the two suites grew by six tests.

Pass 2 — new findings:

**MINOR** · Core / Dimension 4 · `context/harness-reference.md:530` <!-- harness-finding-key context/harness-reference.md:530:MINOR:Core / Dimension 4 -->

The bullet attaches verification only to the fan-out arm, so a reader draws exactly the inference this round's BLOCKER repair removed from `commands/problem.md:372`. The same sentence names two checks where Phase 5 now has three.

**MINOR** · Core / Dimension 4 · `context/critic-brief.md:15` <!-- harness-finding-key context/critic-brief.md:15:MINOR:Core / Dimension 4 -->

Step 1's repair updated lines 13 and 32 but left line 15's parenthetical asserting Core's unconditional activation ("excluding Core, always active"). Resolving that residue the wrong way reproduces the round-1 BLOCKER's failure mode.

**MINOR** · Testing / Dimension 22 · `tests/test_0081_problem_phase5_fanout.py:126` <!-- harness-finding-key tests/test_0081_problem_phase5_fanout.py:126:MINOR:Testing / Dimension 22 -->

The check-3 test pins only that the prose exists, not its consequence. The widened halt sentence could revert to "either check" and the suite would stay green.

**OBS** · AI/LLM / Dimension 15 / Willison · `commands/problem.md:376` <!-- harness-finding-key commands/problem.md:376:OBS:AI/LLM / Dimension 15 / Willison -->

Check 3 makes a pass/fail verdict the orchestrating model computes by reading a subagent's prose — Willison's text-parsed-success-detection hazard, and against CLAUDE.md's LLM/Python boundary. `gates/critic_finding_parser.py` already extracts the panel token, but a subagent's report arrives in context rather than on disk, so a deterministic check costs a temp-file write. Worth naming which of checks 2 and 3 is authoritative if a future round wants the verdict reproducible.

**OBS** · Core / Dimension 7 · `tests/test_0081_critic_brief_panels.py:111` <!-- harness-finding-key tests/test_0081_critic_brief_panels.py:111:OBS:Core / Dimension 7 -->

The diff loosened `assert "It is always active." in step_1` to drop the period. Legitimate — the sentence genuinely gained a qualifier — and compensated by two new tests pinning the replacement text exactly. No fix needed.

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

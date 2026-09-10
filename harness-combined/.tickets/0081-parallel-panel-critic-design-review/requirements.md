# Requirements

**Ticket**: 0081
**Title**: Parallelize multi-panel design-review critic rounds

## Functional Requirements

1. `/problem` Phase 5 must run `panel_detect.py` itself, in-session,
   before spawning any critic agent — `--root` the project root, `--design`,
   and the file list inferred from solution.md's intended changes — to
   obtain `active`/`candidates`/`skipped`.
2. Phase 5 must disposition every `candidates` entry itself (activate or
   defer, one-line reason) to finalize the active-panel set before
   deciding how many agents to spawn — this judgment moves from inside the
   critic subagent (today) to the orchestrating Phase 5 text.
3. If the finalized active-panel set has fewer than 2 non-Core panels,
   Phase 5 must spawn exactly one critic agent with today's unchanged
   brief (the agent still runs its own internal panel detection) — no
   split, no merge step, byte-identical to current behavior.
4. If 2 or more non-Core panels are active, Phase 5 must spawn one critic
   agent per active panel (Core plus problem.md's 5 design-specific
   evaluations in one agent; each other panel alone, with no design-specific
   evaluations added, in its own agent), as parallel Agent tool calls in a
   single message.
5. `critic-brief.md` must gain an optional `Panels: <name>[, <name>...]`
   field in the brief. When present, Step 1 skips its own `panel_detect.py`
   invocation and treats the given names as the fixed active set for that
   agent; when absent, Step 1 behaves exactly as it does today.
6. Phase 5 must merge the parallel agents' reports by concatenation under
   one findings document, preserving every finding's exact structured
   header-line format unchanged, with no fuzzy dedup logic — panel
   assignment in FR-4 guarantees no two agents produce findings under the
   same panel/dimension space.
7. The revise-then-round-2 budget stays 2 total passes (each pass possibly
   parallel-fanned per FR-3/FR-4), never 2 rounds per panel.
8. Secondary-panel escalation must never be automatically triggered by the
   fan-out; `critic-brief.md` and `problem.md` must document it as an
   orchestrator-optional manual step, exercised only after reading the
   merged reports.

## Non-Functional Requirements

1. `critic-brief.md`'s existing severity vocabulary, anti-patterns, and
   Step 1 no-`Panels:`-field behavior are unchanged — this is additive.
2. Parallel agent spawns must be issued as multiple Agent tool calls in one
   message (the harness's own parallel-tool-call convention), never
   sequential calls that defeat the wall-clock benefit.

## Test Strategy

| Type       | Rationale                                                            |
|------------|-------------------------------------------------------------------------|
| Doc-wiring | `critic-brief.md` documents the optional `Panels:` field and its Step 1 skip-detection behavior, additively (no existing Step 1 text removed) |
| Doc-wiring | `commands/problem.md` Phase 5 documents the in-session `panel_detect.py` run, the 2-non-Core-panel threshold, the per-panel spawn split, and the concatenation-only merge |
| Doc-wiring | Phase 5 documents the single-agent fallback for 0–1 non-Core panels, phrased so it cannot be read as always-parallel |
| Doc-wiring | Both files document Secondary-panel escalation as manual-only, not auto-triggered by the split |

## Acceptance Criteria

- A design review with only Core (or Core + 1 other panel) active spawns
  exactly one critic agent, brief unchanged from before this ticket.
- A design review with Core + 2 or more other panels active spawns one
  agent per panel, in parallel, each agent's brief naming only its own
  assigned panel(s).
- The merged findings document contains every finding from every spawned
  agent, none duplicated, none dropped, exact header-line format intact.
- Round budget stays at 2 total revision passes regardless of how many
  panels are active in either pass.

## Open Questions

None.

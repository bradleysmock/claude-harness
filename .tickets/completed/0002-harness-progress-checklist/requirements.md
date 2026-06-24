# Requirements

**Ticket**: 0002
**Title**: Always show a stage-progress checklist for multi-stage harness commands

## Functional Requirements

1. The system must define a single shared "Progress checklist" convention in `context/harness-reference.md`: as the first action of a multi-stage flow, create a `TodoWrite` list with one item per declared stage; mark a stage `in_progress` on start and `completed` on finish; keep exactly one `in_progress`; keep labels short (a few words, to survive UI truncation); on early exit leave the checklist reflecting true state. **One list per run:** a flow entered as a *sub-flow* under a parent (e.g. `build-ticket.md`/`deliver-ticket.md` run under `/autopilot`) does NOT create its own list — it adopts the run's existing list, whose stages the parent already declared.
2. Each multi-stage command/flow must carry, at the top before its first step, a "Progress checklist" block that opens with the unique sentinel `<!-- progress-checklist -->`, declares its stage labels, and references the convention. The seven files: `context/flows/autopilot-ticket.md`, `context/flows/build-ticket.md`, `context/flows/build-spec.md`, `commands/problem.md`, `context/flows/write-spec-ticket.md`, `context/flows/write-spec-spec.md`, `context/flows/deliver-ticket.md`.
3. Labels shared across flows must be byte-identical: `build-ticket.md` and `autopilot-ticket.md` share their first three (Generate specs (if needed) · Build XXXX in worktree · Critic + auto-repair); `deliver-ticket.md` and autopilot's delivery tail share (Merge worktree · Status → done + archive · Cleanup). The test splits each block's label line on ` · ` and compares the relevant elements.
4. The "one list per run" sub-flow rule lives in the convention (FR-1). `build-ticket.md` and `deliver-ticket.md` must each note they may run as a sub-flow under `/autopilot` and then follow that rule (adopt the existing list rather than create a second). The trigger is observable: whether a checklist already exists for this run.
5. The sentinel `<!-- progress-checklist -->` must appear in **exactly** the seven flow files of FR-2 and nowhere else under `commands/`, `context/flows/`, or `skills/`. Sub-flow-only files (`context/flows/stack-advisor.md`, `repair-escalation.md`) and all single-step commands intentionally lack it.

## Non-Functional Requirements

1. DRY: mechanism prose lives once (the convention); flows declare only labels.
2. No behavioral change — display-only.

## Test Strategy

| Type | Rationale |
|------|-----------|
| Unit (content-assertion) | Convention subsection exists; sentinel + expected labels present in the 7 flow files; sub-flow note present in build-ticket & deliver-ticket; shared labels byte-identical (split on ` · `); **exhaustive** sentinel scan finds it in exactly those 7 files. Mirrors `tests/test_ticket_archiving.py`. |

**Limitation (not automatable):** content tests verify the *instructions exist*, not the *runtime behavior* — no test can confirm the model calls `TodoWrite`. The reliability criterion is discharged manually.

## Acceptance Criteria

- 7 flow files carry the sentinel + labels; convention present; sub-flow note present; shared labels identical; exhaustive scan finds the sentinel only in those 7 files.
- All content-assertion tests pass.
- **Manual:** one dry-run each of `/autopilot` and `/build` shows exactly one checklist that advances start→finish — for `/autopilot`, confirm the **delivery sub-stages** (merge/status/cleanup) advance, not a single opaque item.

## Open Questions

(none — design approved by the lead.)

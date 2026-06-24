# Solution

**Ticket**: 0002
**Title**: Always show a stage-progress checklist for multi-stage harness commands

## Approach

Make checklist creation the mandated first action of every multi-stage flow. One shared "Progress checklist" convention defines the mechanism (including a "one list per run" sub-flow rule); each flow declares only its own short stage labels behind a unique sentinel. Instruction-based (todos are agent-driven; a hook cannot inject them) — reliability comes from prominent placement + exact labels, not enforcement.

## Components

| Component | Responsibility |
|-----------|----------------|
| `harness-reference.md` → "Progress checklist" subsection | Single source for *how*: `TodoWrite` first; one `in_progress`; mark `completed`; short labels; true state on early exit; **one list per run — sub-flows adopt the existing list, never create a second**. |
| Per-flow block (7 files) | Opens with sentinel `<!-- progress-checklist -->`, declares labels, points to convention. |
| Sub-flow note in `build-ticket.md` & `deliver-ticket.md` | "May run under `/autopilot` — follow the convention's one-list-per-run rule." |
| Content-assertion tests | Sentinel exhaustive present/absent, labels, convention, sub-flow note, shared-label equality. |

## Label Table

| Flow file | Stage labels |
|-----------|--------------|
| `autopilot-ticket.md` | Generate specs (if needed) · Build XXXX in worktree · Critic + auto-repair · Merge worktree · Status → done + archive · Cleanup |
| `build-ticket.md` | Generate specs (if needed) · Build XXXX in worktree · Critic + auto-repair · Present diff (Checkpoint 2) |
| `deliver-ticket.md` | Merge worktree · Status → done + archive · Cleanup |
| `build-spec.md` | Generate spec (if needed) · Run gate engine · Produce artifact |
| `problem.md` | Match its actual phases: Clarity check · Claim ticket · Problem · Requirements · Tech-stack advisor (if new app) · Solution · Critic loop · Checkpoint 1 |
| `write-spec-ticket.md` / `write-spec-spec.md` | Analyze (spec vs task DAG) · Write spec(s) |

Autopilot = full pipeline (build stages + deliver sub-stages) so the longest tail is visible, not one opaque "Auto-deliver". Shared labels (build/autopilot first three; deliver/autopilot tail) are byte-identical (FR-3). The `problem.md` list mirrors the real phases, conditional ones suffixed "(if new app)".

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `TodoWrite` tool | Native Claude Code UI that renders `✔/◼/◻` + timer. |
| Sentinel `<!-- progress-checklist -->` | Unique structural marker → drift-proof present/absent tests (avoids matching the prose phrase the convention itself contains). |
| One-list-per-run rule in the convention | Both `build-ticket` and `deliver-ticket` are sub-flows under autopilot; a single convention rule guards both (no per-flow duplication). |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit (content) | Convention subsection (incl. one-list-per-run rule) exists. |
| FR-2/FR-3 | Unit (content) | Sentinel + labels in the 7 files; shared labels equal after splitting label line on ` · ` and comparing the shared elements. |
| FR-4 | Unit (content) | Sub-flow note present in `build-ticket.md` and `deliver-ticket.md`. |
| FR-5 | Unit (content) | **Exhaustive** scan: sentinel in exactly the 7 flow files, absent everywhere else under `commands/`, `context/flows/`, `skills/`. |
| Reliability | Manual | Dry-run `/autopilot` + `/build`: one checklist advancing; for autopilot, deliver sub-stages advance. |

## Tradeoffs

- **Instruction over enforcement**: todos are agent-driven; best-effort, maximized by placement. Content tests verify presence, not runtime (hence the manual step).
- **Sentinel over heading-text match**: one extra token per file buys an unambiguous, exhaustive test.

## Risks

- **Model still skips it** → mandated first action + labels; not fully eliminable.
- **Double / opaque checklist under autopilot** → one-list-per-run rule + autopilot declaring the full pipeline incl. deliver sub-stages.
- **Label drift** → identical shared labels (FR-3) + this single label table.

## Implementation Order

1. Fix the contracts both blocks depend on: the sentinel token, the one-list-per-run sub-flow rule, and the shared-label set.
2. Add the "Progress checklist" convention (incl. sub-flow rule) to `harness-reference.md`.
3. Add the per-flow block to `autopilot-ticket.md` (full pipeline labels).
4. Add blocks + sub-flow notes to `build-ticket.md` and `deliver-ticket.md`, reusing the shared labels from step 1.
5. Add blocks to `build-spec.md`, `problem.md` (match real phases), `write-spec-ticket.md`, `write-spec-spec.md`.
6. Write content-assertion tests (FR-1..FR-5, incl. the exhaustive negative scan).

# Solution

**Ticket**: 0013
**Title**: Build --dry-run mode

## Approach

Add a `--dry-run` flag to `/build` (ticket mode only; rejected with an error in spec mode). When set, the build flow follows the same path as a normal build through spec generation, gate execution, and critic invocation, but intercepts all file writes. Specs are generated in-memory by passing `dry_run=True` to suppress the file-write step in `write-spec-ticket.md` Step 5. Gates run against generated code via `gate_run` (spec-mode) inside a dedicated temp directory that is cleaned up regardless of outcome. The critic is invoked as `Phase: design` with ticket artifacts only (no raw generated code — spec metadata in structured form: id, target_file, description, acceptance_criteria); generated code's file scope is inferred from solution.md per the existing design-phase panel-activation rule. No status transition occurs; no worktree is created; Step 7a (auto-repair loop) is suppressed via `DRY_RUN` check placed at Step 7a entry, not Step 7.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| Flag parser (`build.md`) | Detect `--dry-run` in `$ARGUMENTS`; set `DRY_RUN=true`; reject with error in spec mode; strip flag, pass remainder as ticket argument | Pre-mode-selection |
| Spec-gen no-write path | Call spec-gen with `dry_run=True` boolean; skip `write-spec-ticket.md` Step 5 write; return in-memory spec objects; display spec summaries (structured metadata only) | Returns list of spec objects |
| Sandboxed gate runner | Run `gate_run` on each spec's code inside a temp dir created and unconditionally cleaned up by the dry-run flow; accumulate gate results; write `gate-findings.md` atomically after all specs complete | Temp dir lifecycle owned by dry-run flow, not `gate_run` |
| Dry-run critic invocation | Spawn critic as `Phase: design` with ticket artifacts + structured spec metadata (id, target_file, description, acceptance_criteria — no raw code); check `DRY_RUN=true` at Step 7a entry to suppress auto-repair loop | Critic logs invocation ID to structured session log |
| Dry-run report assembler | Collect sections: spec plan, gate findings, critic findings, limitation labels into a structured `DryRunReport` object | Distinct from rendering |
| Dry-run report renderer | Format and display `DryRunReport`: header, spec summaries, gate findings, critic findings, "would write" plan, limitation labels, proceed prompt | Reads only `DryRunReport` |

## Tech Choices

| Choice | Rationale |
|---|---|
| `Phase: design` for critic (no raw code inline) | Avoids untrusted LLM-generated code reaching a tool-capable agent's context; structured metadata only. Design-phase panel activation from `solution.md` is deterministic and defined. |
| `dry_run=True` parameter in spec-gen | Single intercept point at write step; no duplication of spec-generation logic. |
| Temp dir owned by dry-run flow (not `gate_run`) | Structural containment: the caller creates, uses, and cleans the temp dir; `gate_run` writes within it. No reliance on `gate_run`'s internal cleanup behavior. |
| Assembler/renderer split for output | Divergent change isolation: gate format changes touch only assembler; display format changes touch only renderer. |
| `DRY_RUN` check at Step 7a entry | Critic still runs (Step 7); repair loop does not (Step 7a). Placement is explicit, not implicit. |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|---|---|---|
| FR-1 (flag parse) | Unit | `--dry-run` detected, stripped, ticket arg extracted correctly |
| FR-1 (spec-mode rejection) | Unit | `--dry-run` + spec-mode argument → error, no further execution |
| FR-2–3 | Integration | Fixture ticket dry run → `gate-findings.md` exists; gate phases invoked |
| FR-4 (critic invoked) | Integration | Critic invocation ID logged to structured session log; assert log entry exists |
| FR-5 | Integration | "would write: <file>" line present for each spec `target_file` |
| FR-6–7 | Integration | No path created under `.worktrees/`, `.harness/specs/`, `.harness/tasks/`; temp dir cleaned up |
| FR-8 | Integration | `status.md` remains `solution` after dry run |
| FR-9 (DRY RUN label) | Integration | Rendered output contains "=== DRY RUN — no files written ===" header |
| FR-9 (gate coverage warning) | Integration | Rendered output contains "Gate coverage: indicative only" warning |
| FR-10 (no spec persistence) | Unit | `dry_run=True` returns spec objects; `.harness/specs/` unchanged |
| FR-11 | Integration | Rendered output ends with proceed prompt |
| Step 7a suppression | Integration | Critic returns BLOCKER finding; assert no repair commit, no worktree |

## Tradeoffs

- **Chose `Phase: design` critic + structured metadata only**: Eliminates prompt-injection surface from generated code. Tradeoff: critic has no visibility into generated code quality at the syntax/style level; code-phase panels do not fire. Label in output: "Critic coverage: design-phase panels only (code-phase panels require live build)."
- **Chose temp dir owned by dry-run flow**: `gate_run`'s internal temp behavior is irrelevant; containment is structural. Tradeoff: small added orchestration complexity.
- **Assembler/renderer split**: Clean divergent-change isolation. Tradeoff: two components instead of one; justified by seven distinct output concerns.
- **Accepting risk of**: Gate results differ from live-build results (no cross-file integration). Label: "Gate coverage: indicative only — cross-file integration issues not surfaced."

## Risks

- `Phase: design` critic with structured metadata may produce sparser findings than code-phase critic. Mitigate: output labels explicitly state limitation; lead can follow with live build for full code-phase review.
- Temp dir cleanup failure on hard process kill. Mitigate: temp dirs go under `.harness/dry-run-tmp/` (gitignored); a startup check removes stale dirs from prior interrupted runs.

## Implementation Order

1. Unit test: flag parsing, spec-mode rejection. Implementation: flag parser.
2. Integration test skeleton: fixture ticket dry run → `.worktrees/` empty, `status.md` unchanged, DRY RUN header present. (Red.)
3. Unit test: `dry_run=True` suppresses spec write. Implementation: spec-gen no-write path.
4. Unit test: assembler produces `DryRunReport` with correct sections. Implementation: assembler.
5. Integration test: temp dir created and cleaned; `gate-findings.md` written. Implementation: sandboxed gate runner.
6. Integration test: critic invocation ID in session log. Implementation: dry-run critic invocation + Step 7a suppression.
7. Implementation: renderer. All integration tests pass (green).
8. Document `dry_run` parameter in `write-spec-ticket.md`; document Step 7a `DRY_RUN` check in `build-ticket.md`.

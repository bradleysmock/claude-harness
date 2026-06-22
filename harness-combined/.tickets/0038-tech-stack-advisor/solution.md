# Solution

**Ticket**: 0038
**Title**: Tech Stack Advisor

## Approach

Add a `stack_advisor` sub-procedure to `commands/problem.md` that fires between Phase 3 (requirements) and Phase 4 (solution) when a new-artifact signal is detected. The advisor reads `_standards.md`, scans the project root for existing manifest files, and composes a proposal. The lead approves or amends inline; the result is written into `requirements.md § Tech Stack` before solution planning begins. No new Python modules — pure command-prose logic.

## Components

| Component | Responsibility | Interface |
|-----------|---------------|-----------|
| `new_artifact_detector` | Classify request as new-app / new-service / new-UI / feature-addition | Reads request text + project root manifests; returns `{type, confidence}` |
| `stack_signal_collector` | Gather signals: `_standards.md` keys, manifest language, explicit request text | Returns ordered list of `{signal, source, priority}` |
| `proposal_builder` | Compose the stack proposal table with rationale from collected signals | Returns Markdown table |
| `stack_approval_gate` | Present proposal to lead; handle approve/modify/reject | Writes approved stack to `requirements.md`; blocks on rejection until stack is provided |
| Guard in `commands/problem.md` | Check for existing `## Tech Stack` section and `--no-stack-check` flag; skip if present | None |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Command-prose only (no new Python module) | Keeps the change contained to `commands/problem.md` and optionally `commands/autopilot.md`; no new server.py surface |
| Signals ranked: _standards.md > manifest files > request text > defaults | Explicit lead configuration always wins; project convention second; request intent third; training-data default last |
| Single interactive round-trip | NFR-1: one proposal + one response, not a wizard |
| Approval stored in `requirements.md § Tech Stack` | Existing read path in `/build` already honors this section; no new persistence mechanism needed |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | "new FastAPI microservice" → type=service; "add /health endpoint" → type=feature |
| FR-2        | Integration | New-service request → proposal table appears before Checkpoint 1 |
| FR-3        | Unit        | `_standards.md` with `language: Go` → proposal defaults to Go |
| FR-4        | Unit        | Project root has `package.json` → proposal includes Node/TS |
| FR-5        | Integration | Lead approves → `## Tech Stack` written to requirements.md |
| FR-6        | Integration | Lead modifies proposal → modified stack written |
| FR-7        | Integration | Lead rejects → follow-up prompt; custom stack recorded |
| FR-8        | Integration | Existing `## Tech Stack` section → `/build` reads it, no re-prompt |
| FR-9        | Integration | Existing `## Tech Stack` section → advisor not triggered in `/problem` |
| FR-10       | Integration | `--no-stack-check` flag → advisor skipped, proceeds to Checkpoint 1 |
| NFR-2       | Unit        | "add endpoint to user service" → detector returns feature-addition with zero misclassification |

## Tradeoffs

- **Chose command-prose over a new MCP tool**: Keeps the change reviewable as a markdown diff; a dedicated MCP tool would enable richer signal collection but adds server.py surface and deployment complexity.
- **Chose single round-trip over wizard**: Reduces friction for leads who know what they want; the trade-off is that nuanced stack decisions (e.g., "I want Rust but only for the hot path") need a follow-up `/replan`.
- **Accepting risk of**: false-negative detection (feature ticket misclassified as new-app) triggers the advisor unnecessarily; mitigated by `--no-stack-check` escape hatch and low cost of one extra interaction.

## Risks

- **LLM hallucination on stack rationale**: Mitigated by grounding proposals in `_standards.md` and manifest files first; LLM fills gaps only when no explicit signal exists.
- **Detection false positives on ambiguous requests**: Mitigated by conservative classifier (prefer feature-addition if uncertain) and `--no-stack-check` escape.
- **`_standards.md` schema inconsistency**: If `_standards.md` uses varied key names (`language:` vs `Language:` vs `tech_stack:`), the collector must normalize. Specify exact accepted keys in implementation.

## Implementation Order

1. Add `new_artifact_detector` logic to `commands/problem.md` (heuristic: keywords "new", "build a", "create a", "initialize" + absence of an existing codebase manifest at project root)
2. Add `stack_signal_collector` logic (read `_standards.md` for language/framework keys, scan root for manifests, extract explicit request signals)
3. Add `proposal_builder` (compose Markdown table: Choice | Rationale, one row per stack dimension)
4. Add `stack_approval_gate` (present table, await lead input, write to `requirements.md § Tech Stack` on approve/modify)
5. Add guard: skip if `## Tech Stack` already populated in `requirements.md`; skip if `--no-stack-check` flag present
6. Update `commands/autopilot.md` (if exists) with the same advisor call for standalone new-app invocations
7. Update `context/harness-reference.md` to document the advisor flow and `--no-stack-check` flag

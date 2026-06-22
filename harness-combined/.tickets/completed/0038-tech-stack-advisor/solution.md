# Solution

**Ticket**: 0038
**Title**: Tech Stack Advisor

## Approach

Add a `stack_advisor` sub-procedure extracted to `context/flows/stack-advisor.md` (keeping `commands/problem.md` legible) that fires between Phase 3 (requirements) and Phase 4 (solution) when a new-artifact signal is detected. The advisor reads only structured key-value fields from `_standards.md` and checks manifest file existence at the project root — it does not ingest arbitrary file content into the LLM context. The lead approves or amends inline; the result is written into `requirements.md § Tech Stack` before solution planning begins. Rejection retries are capped at 2; a placeholder is written on exhaustion. No new Python modules — pure command-prose logic.

## Components

| Component | Responsibility | Interface |
|-----------|---------------|-----------|
| Guard (first) | Check for existing `## Tech Stack` section and `--no-stack-check` flag; skip entire advisor if present | None; pure branch |
| `new_artifact_detector` | Classify request as `new-app \| new-service \| new-ui \| feature-addition` with `confidence: high\|medium\|low`; trigger only on `high` confidence; default to `feature-addition` on `medium\|low` | Reads keyword signals AND manifest-absent signal; BOTH must be present for `high` confidence |
| `stack_signal_collector` | Gather structured signals only: `_standards.md` key-value fields (`language:`, `framework:`, `runtime:`), manifest file existence (type detection, no content read), explicit language/framework words in request | Returns ordered `[{choice, value, source, priority}]` |
| `proposal_builder` | Compose the stack proposal table from collected signals with one-line rationale per row | Returns Markdown table |
| `stack_approval_interaction` | Present proposal to lead; handle approve/modify/reject with max-2-retry termination; write to `requirements.md § Tech Stack` or placeholder on exhaustion | Side-effect: writes `requirements.md`; returns `{approved: bool, stack: str}` |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Flow file in `context/flows/stack-advisor.md`, not inline in `commands/problem.md` | Keeps problem.md legible; flow file is independently auditable; follows existing pattern (flows/build-ticket.md, etc.) |
| Structured key extraction only from `_standards.md` and manifests | Closes lethal-trifecta risk: LLM does not see raw `_standards.md` prose or arbitrary manifest content |
| Signals ranked: _standards.md > manifest exists > request text > defaults | Explicit lead config wins; project convention second; request intent third; training-data default last |
| Require BOTH keyword AND absent-manifest for high-confidence new-artifact | Operationalizes conservative classifier; prevents false positives when "new" appears in feature requests on existing codebases |
| Single interactive round-trip with max-2 rejection retries | NFR-1: one proposal + one response, not a wizard; max-2 ensures fail-closed exit path |
| Approval stored in `requirements.md § Tech Stack` | Existing read path in `/build` already honors this section; no new persistence mechanism needed |
| Advisor scoped to `/problem` only | Avoids adding a trigger surface to `/autopilot`; `/autopilot` already reads the recorded stack |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1/NFR-2  | Unit        | ≥8 classification cases: new app (no manifest) → high/trigger; feature + manifest → feature; "new" + manifest present → feature; ambiguous no keywords → feature; porting service → feature; refactor into standalone → feature; new UI subdir → high/trigger; monorepo new-service sibling → high/trigger |
| FR-3        | Unit        | `_standards.md` with `language: Go` → proposal defaults to Go; prose in _standards.md not ingested |
| FR-4        | Unit        | `package.json` present at root → Node/TS signal detected; file not read past existence + name check |
| FR-5        | Integration | Lead approves → `## Tech Stack` written to requirements.md |
| FR-6        | Integration | Lead modifies proposal → modified stack written |
| FR-7        | Integration | Lead rejects once → re-prompt; lead rejects twice → placeholder written, advisor exits |
| FR-8        | Integration | Existing `## Tech Stack` section → `/build` reads it, no re-prompt |
| FR-9        | Integration | Existing `## Tech Stack` section → guard fires, advisor not triggered in `/problem` |
| FR-10       | Integration | `--no-stack-check` flag → guard fires, advisor skipped, proceeds to Checkpoint 1 |
| FR-11       | Integration | `/autopilot` on ticket with `## Tech Stack` → uses recorded stack, does not re-trigger advisor |

## Tradeoffs

- **Chose command-prose over a new MCP tool**: Keeps the change reviewable as a markdown diff; a dedicated MCP tool would enable richer signal collection but adds server.py surface and deployment complexity.
- **Chose single round-trip over wizard**: Reduces friction for leads who know what they want; the trade-off is that nuanced stack decisions (e.g., "I want Rust but only for the hot path") need a follow-up `/replan`.
- **Accepting risk of**: false-negative detection (feature ticket misclassified as new-app) triggers the advisor unnecessarily; mitigated by `--no-stack-check` escape hatch and low cost of one extra interaction.

## Risks

- **LLM hallucination on stack rationale**: Mitigated by grounding proposals in `_standards.md` and manifest files first; LLM fills gaps only when no explicit signal exists.
- **Detection false positives on ambiguous requests**: Mitigated by conservative classifier (prefer feature-addition if uncertain) and `--no-stack-check` escape.
- **`_standards.md` schema inconsistency**: If `_standards.md` uses varied key names (`language:` vs `Language:` vs `tech_stack:`), the collector must normalize. Specify exact accepted keys in implementation.

## Implementation Order

1. Write `context/flows/stack-advisor.md` shell with guard first: read `requirements.md`, check for `## Tech Stack` presence; check `--no-stack-check` flag; skip (return) if either is true
2. Add `new_artifact_detector` section: keyword scan + manifest-absent check; output `{type, confidence}`; `high` requires BOTH signals; default `feature-addition` on `medium|low`
3. Add `stack_signal_collector` section: read `_standards.md` structured keys only (language, framework, runtime); detect manifest file existence (no content read); extract explicit language/framework words from request text
4. Add `proposal_builder` section: compose Markdown table from signals; one row per dimension; include rationale source (`_standards.md` / manifest / request / default)
5. Add `stack_approval_interaction` section: present table; handle approve/modify/reject; max-2 rejection retries; write `## Tech Stack` to `requirements.md` or placeholder on exhaustion
6. Wire `stack-advisor.md` call into `commands/problem.md` between Phase 3 and Phase 4 (one-line `@context/flows/stack-advisor.md` include)
7. Update `context/harness-reference.md` to document the advisor flow, `--no-stack-check` flag, and the `## Tech Stack` contract for `/build`

# Requirements

**Ticket**: 0038
**Title**: Tech Stack Advisor

## Functional Requirements

1. The system must detect when a `/problem` request describes a new application, microservice, or UI component — distinguished from a feature addition to an existing codebase.
2. When a new artifact is detected, the system must propose a tech stack before writing any implementation files, listing each choice (language, runtime, framework, key libraries) with a one-line rationale.
3. The proposal must incorporate signals from `_standards.md` (if present) as the highest-priority input, overriding training-data defaults. Only the structured key-value fields `language`, `framework`, and `runtime` are read (case-insensitive key matching; aliases such as `tech_stack` are not accepted). Unrecognized keys are silently ignored. Arbitrary prose content in `_standards.md` is not ingested into the LLM context.
4. The proposal must incorporate explicit signals from the request text and the project root's existing language/tooling, detected from manifest file existence and known top-level keys only (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`). Raw manifest file content is not read into the LLM context.
5. The system must present the proposal to the lead and require explicit approval, modification, or rejection before proceeding.
6. On approval (or after modification), the system must write the approved stack into the `## Tech Stack` section of `requirements.md` for the ticket.
7. On rejection, the system must prompt the lead to specify the desired stack and record that instead. A **rejection** is an explicit refusal with no alternative stack provided; an **invalid response** is an empty or unparseable input. If the lead makes two consecutive rejections-without-specification (or two invalid responses, or one of each), the system must write an empty `## Tech Stack` placeholder (`<!-- stack not specified — fill in before /build -->`) and continue to Checkpoint 1, rather than looping indefinitely. The lead must receive a brief notice before the placeholder is written.
8. Once a `## Tech Stack` section exists in `requirements.md`, subsequent `/build` invocations must read and honor it without re-prompting.
9. Tickets that already have a populated `## Tech Stack` section must not trigger the advisor flow.
10. The advisor flow must be skippable via a `--no-stack-check` flag for operators who have fully specified the stack in `_standards.md`.
11. The advisor fires in `/problem` only. `/autopilot` (standalone mode) honors an existing `## Tech Stack` section in `requirements.md` if the ticket already exists; it does not independently trigger the advisor.

## Non-Functional Requirements

1. The proposal step must add no more than one interactive round-trip to the `/problem` pipeline (not a multi-step wizard).
2. The detection heuristic for "new artifact" must classify new-app/service/UI requests correctly and produce fewer than 5% false positives on additive feature tickets in a representative test suite of at least 8 cases spanning: plain new-app (no manifest), feature addition with manifest present, ambiguous/no-keyword request, "new" keyword + manifest present, porting an existing service, adding a submodule, refactoring into a standalone service, new UI component with no manifest.

## Test Strategy

| Type        | Rationale                                                         |
|-------------|-------------------------------------------------------------------|
| Unit        | Detection heuristic: ≥8 classification cases including edge cases |
| Unit        | Stack signal collector: _standards.md key extraction (case-insensitive; aliases rejected; prose ignored); manifest type detection |
| Unit        | Rejection termination: 2 rejections → placeholder written; 1 rejection + 1 invalid → placeholder written |
| Integration | Full `/problem` flow: proposal presented and written to req.md    |
| Integration | Existing Tech Stack section: advisor not triggered                |
| Integration | `--no-stack-check` flag: advisor skipped                          |

## Acceptance Criteria

- `/problem` with "build a new FastAPI service" presents a stack proposal before Checkpoint 1 and writes the approved stack to `requirements.md`.
- `/problem` with "add a `/health` endpoint to the existing user service" does NOT trigger the advisor.
- `/problem` with "new" keyword present but `pyproject.toml` already in project root → classified as feature-addition, advisor NOT triggered.
- A ticket whose `requirements.md` already has `## Tech Stack` populated does NOT re-trigger the advisor on subsequent `/build`.
- `_standards.md` containing `language: Go` causes the proposal to default to Go, not Python, regardless of training-data frequency.
- `--no-stack-check` skips the proposal entirely and proceeds to Checkpoint 1.
- Lead rejects twice with no valid response → `requirements.md` has `<!-- stack not specified — fill in before /build -->` placeholder; advisor exits without blocking.

## Open Questions

None. The `/autopilot` scope question is resolved: the advisor fires in `/problem` only (FR-11). `/autopilot` honors an already-written `## Tech Stack` section but does not independently trigger the advisor flow.

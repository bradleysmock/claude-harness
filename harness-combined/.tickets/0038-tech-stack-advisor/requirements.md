# Requirements

**Ticket**: 0038
**Title**: Tech Stack Advisor

## Functional Requirements

1. The system must detect when a `/problem` request describes a new application, microservice, or UI component — distinguished from a feature addition to an existing codebase.
2. When a new artifact is detected, the system must propose a tech stack before writing any implementation files, listing each choice (language, runtime, framework, key libraries) with a one-line rationale.
3. The proposal must incorporate signals from `_standards.md` (if present) as the highest-priority input, overriding training-data defaults.
4. The proposal must incorporate explicit signals from the request text (e.g., "a Python service", "a React component") and the project root's existing language/tooling (detected from manifest files: `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, etc.) as secondary inputs.
5. The system must present the proposal to the lead and require explicit approval, modification, or rejection before proceeding.
6. On approval (or after modification), the system must write the approved stack into the `## Tech Stack` section of `requirements.md` for the ticket.
7. On rejection, the system must prompt the lead to specify the desired stack and record that instead.
8. Once a `## Tech Stack` section exists in `requirements.md`, subsequent `/build` and `/autopilot` invocations must read and honor it without re-prompting.
9. Tickets that already have a populated `## Tech Stack` section must not trigger the advisor flow.
10. The advisor flow must be skippable via a `--no-stack-check` flag for operators who have fully specified the stack in `_standards.md`.

## Non-Functional Requirements

1. The proposal step must add no more than one interactive round-trip to the `/problem` pipeline (not a multi-step wizard).
2. The detection heuristic for "new artifact" must produce zero false positives on purely additive feature tickets (adding an endpoint to an existing service).

## Test Strategy

| Type        | Rationale                                                         |
|-------------|-------------------------------------------------------------------|
| Unit        | Detection heuristic: new-app vs. feature-addition classification  |
| Unit        | Stack proposal builder: _standards.md override, manifest signals  |
| Integration | Full `/problem` flow: proposal presented and written to req.md    |
| Integration | Existing Tech Stack section: advisor not triggered                |
| Integration | `--no-stack-check` flag: advisor skipped                          |

## Acceptance Criteria

- `/problem` with "build a new FastAPI service" presents a stack proposal before Checkpoint 1 and writes the approved stack to `requirements.md`.
- `/problem` with "add a `/health` endpoint to the existing user service" does NOT trigger the advisor.
- A ticket whose `requirements.md` already has `## Tech Stack` populated does NOT re-trigger the advisor on subsequent `/build`.
- `_standards.md` containing `language: Go` causes the proposal to default to Go, not Python, regardless of training-data frequency.
- `--no-stack-check` skips the proposal entirely and proceeds to Checkpoint 1.

## Open Questions

- Should the advisor also fire during `/autopilot` (standalone mode, no existing ticket)? Assumed yes for new-app descriptions.

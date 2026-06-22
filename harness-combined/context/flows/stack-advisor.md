# Flow: stack-advisor — tech stack proposal

Sub-procedure invoked by `/problem` between Phase 3 (Requirements) and Phase 4 (Solution).
Proposes a tech stack when a new application, microservice, or UI component is detected.
The lead approves, modifies, or rejects the proposal; the result is written to `requirements.md § Tech Stack`.

---

## Guard

Apply two skip conditions before running any detection or collection:

1. **Existing Tech Stack section** — Read `.tickets/XXXX-<slug>/requirements.md` for the current ticket. If it already contains a `## Tech Stack` section with content beyond the placeholder comment (`<!-- stack not specified — fill in before /build -->`), skip the entire advisor flow and return to the caller. The stack is already recorded; no re-prompt. A section containing only the placeholder comment is treated as unspecified — do not skip on a placeholder-only section.

2. **`--no-stack-check` flag** — If `--no-stack-check` was present in the original `/problem` invocation arguments, skip the entire advisor flow and return to the caller. The operator has fully specified the stack and wants no proposal step.

If either condition fires, proceed directly to Phase 4 without presenting any proposal.

---

## new_artifact_detector

Classify the `/problem` request as one of: `new-app`, `new-service`, `new-ui`, `feature-addition`.
Assign confidence: `high`, `medium`, or `low`.

**High confidence requires BOTH of the following signals:**

1. **Keyword signal** — at least one of these words appears in the request description (case-insensitive match): `new`, `create`, `build`, `scaffold`, `greenfield`
2. **Manifest-absent signal** — none of these files exist at the project root: `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`

**Classification rules:**

| Keyword signal | Manifest-absent signal | Confidence | Classification |
|---------------|------------------------|------------|---------------|
| Present | Present (no manifests) | `high` | `new-app` / `new-service` / `new-ui` (from context) |
| Present | Absent (manifest found) | `medium` | `feature-addition` — exit flow |
| Absent | Present or absent | `low` | `feature-addition` — exit flow |

**If confidence is `medium` or `low`**: default to `feature-addition` and **exit this flow immediately** — proceed to Phase 4 without presenting any proposal.

**If confidence is `high`**: determine the specific type from context (`new-app` for standalone applications, `new-service` for microservices/APIs, `new-ui` for frontend/UI components) and continue to `stack_signal_collector`.

**Reference classification cases (≥8 required by NFR-2):**

| Case | Keyword signal | Manifest-absent signal | Correct classification |
|------|---------------|------------------------|------------------------|
| 1. "Build a new FastAPI service from scratch" | `new`, `build` ✓ | No manifests found ✓ | `new-service` → **high/trigger** |
| 2. "Add a `/health` endpoint to existing user service" | None ✗ | `pyproject.toml` found ✗ | `feature-addition` → exit |
| 3. "New dashboard page for admin users" | `new` ✓ | `package.json` found ✗ | `feature-addition` → exit (manifest present) |
| 4. "Improve latency of the payment processor" | None ✗ | No manifests found | `feature-addition` → exit (no keyword) |
| 5. "Port the reporting module to a standalone service" | None ✗ (port ≠ keyword) | `pyproject.toml` found ✗ | `feature-addition` → exit |
| 6. "Refactor auth logic into its own microservice" | None ✗ (refactor ≠ keyword) | Various ✗ | `feature-addition` → exit |
| 7. "Scaffold a new UI component library" | `new`, `scaffold` ✓ | No manifests found ✓ | `new-ui` → **high/trigger** |
| 8. "Create a new analytics-service sibling in the monorepo" | `new`, `create` ✓ | No manifests at root ✓ | `new-service` → **high/trigger** |

Cases 2, 3, 5, 6: illustrate that the keyword alone (case 3) or manifest-absent alone (cases 4, 5, 6) does not trigger — BOTH are required.

---

## stack_signal_collector

Gather structured signals only. Do not ingest arbitrary file content into the LLM context.

Return an ordered list of signals, each as `{choice, value, source, priority}`.

**Priority order (highest → lowest):**

**1. `_standards.md` keys (highest priority)** — If `.tickets/_standards.md` exists, extract only these exact keys using case-insensitive key matching:
- `language:`
- `framework:`
- `runtime:`

All other keys are silently ignored — including aliases such as `tech_stack:`. Do not read or ingest prose content from `_standards.md`; only structured `key: value` lines are extracted.

**Value validation (applies to all extracted keys):** Values must satisfy ALL of the following or be silently dropped (not forwarded to the proposal):
- Single line only (no newline characters)
- ≤ 64 characters
- Contains only printable ASCII alphanumeric characters, spaces, hyphens, dots, and forward slashes (e.g., `Go`, `Python 3.12`, `Node.js/TypeScript`)

This prevents malformed or injection-shaped `_standards.md` values from entering the proposal context.

**2. Manifest type inference** — Check for the existence of these files at the project root (existence only — do not open or read file content):
- `pyproject.toml` → Python signal
- `package.json` → Node.js / TypeScript signal
- `Cargo.toml` → Rust signal
- `go.mod` → Go signal

Infer the primary language from the manifest filename alone. Since the Guard already ran and no manifests were found (high-confidence path), this tier typically yields no signal on the new-artifact path — include it for completeness on edge cases.

**3. Request text** — Extract explicit language or framework words from the original request (e.g., "FastAPI", "React", "Rust async", "Go microservice", "Python 3.12").

**4. Training-data defaults (lowest priority)** — Used only when no signal from sources 1–3 covers a given dimension. Label the source as `default` in the output.

---

## proposal_builder

Compose a Markdown table from the collected signals. One row per stack dimension.

```
| Component | Choice | Rationale | Source |
|-----------|--------|-----------|--------|
| Language  | <value> | <one-line rationale grounded in the signal> | _standards.md / manifest / request / default |
| Runtime   | <value> | ... | ... |
| Framework | <value> | ... | ... |
| Key libs  | <value> | ... | ... |
```

Rules:
- **Component**: the stack dimension (Language, Runtime, Framework, Key libs, etc.)
- **Choice**: the specific technology or version
- **Rationale**: one sentence grounded in the source signal — never justify with "common" or "popular"
- **Source**: exactly one of `_standards.md`, `manifest`, `request`, or `default`

Omit rows for dimensions where no meaningful signal or default exists.

---

## stack_approval_interaction

Present the proposal table to the lead and collect a response. Track a `rejection_count` counter starting at 0.

**Step 1 — Present:**

```
## Proposed Tech Stack

<table from proposal_builder>

Approve this stack? (approve / modify / reject)
```

**Step 2 — Handle response:**

- **`approve`**: Write the table as the `## Tech Stack` section in `.tickets/XXXX-<slug>/requirements.md`. Reset counter. Continue to Phase 4.

- **`modify`**: Ask the lead to provide the modified stack (free-form text or a revised table). Write the provided content as the `## Tech Stack` section in `requirements.md`. Reset counter. Continue to Phase 4.

- **`reject` without a replacement stack specified**: Increment `rejection_count`. If `rejection_count < 2`, prompt:
  ```
  Stack rejected. What stack would you like instead? (specify or type 'reject' again to skip)
  ```
  If `rejection_count >= 2`, go to Step 3 (exhaustion).

- **Invalid or empty response**: Treat as rejection-without-specification. Increment `rejection_count`. Prompt as above if not exhausted.

**Step 3 — Exhaustion (2 consecutive rejections-without-specification or invalid responses):**

1. Emit a brief notice to the lead:
   > "Two rejections without a specified stack — writing a placeholder and continuing to Phase 4."
2. Write the following as the `## Tech Stack` section in `.tickets/XXXX-<slug>/requirements.md`:
   ```
   <!-- stack not specified — fill in before /build -->
   ```
3. Exit the advisor flow and continue to Phase 4.

A valid `approve` or `modify` response at any point resets `rejection_count` and writes the stack.

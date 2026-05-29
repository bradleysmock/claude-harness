---
name: critique
description: Apply domain-specialist panels to the current diff or specified files — Python idioms, HTTP/API design, UI patterns, AI/LLM security — each with a distinct mental model, not just a harder general scan. Also produces a Codebase Patterns section that looks beyond the changed files to surface systemic habits. TRIGGER when the user wants a specific expert lens applied to a change, names a domain ("security review", "Python idioms", "what would an API designer say"), or asks for panel review (e.g. "critique the auth route", "panel review of the new handler", "what's wrong with this from an API design perspective"). SKIP for ticket-scoped post-build reviews (use the review skill, which reads problem/requirements/solution as baseline), for general correctness or style checks (use /code-review), and when the user only wants lint output (use /gate).
---

# Expert Code Critique

Conduct a structured expert critique. Read every file in scope before writing a single finding. The output covers two scopes: **this change** (findings specific to the changed files) and **codebase patterns** (what this change reveals about systemic habits across the broader codebase).

---

## Step 1: Determine Active Panels

Based on the files in scope, determine which panels apply. Announce the active panels before reading any code or panel files.

`${CLAUDE_PLUGIN_ROOT}` is the root of the installed plugin and is injected at invocation time. If unset, resolve it as the directory containing this skill file.

| Files in scope | Panel | File |
|----------------|-------|------|
| Any file | **Core** | `${CLAUDE_PLUGIN_ROOT}/context/panels/core.md` |
| `**/*.py`, or `pyproject.toml` / `setup.py` / `setup.cfg` / `requirements.txt` present | **Python** | `${CLAUDE_PLUGIN_ROOT}/context/panels/python.md` |
| `**/*.ts`, `**/*.tsx`, `**/*.js`, `**/*.mjs`, `**/*.cjs`, `package.json`, `tsconfig.json` | **TypeScript/JS** | `${CLAUDE_PLUGIN_ROOT}/context/panels/typescript.md` |
| `@angular/core` in `package.json`; `angular.json`; `**/*.component.{ts,html}`, `**/*.service.ts`, `**/*.module.ts`, `**/*.directive.ts`, or `**/*.pipe.ts` in scope | **Angular** | `${CLAUDE_PLUGIN_ROOT}/context/panels/angular.md` |
| `react` in `package.json`; `**/*.{jsx,tsx}` with React imports or component patterns; `next.config.*`, `remix.config.*`, or `vite.config.*` with `@vitejs/plugin-react` | **React** | `${CLAUDE_PLUGIN_ROOT}/context/panels/react.md` |
| `vue` in `package.json`; `**/*.vue` files; `nuxt.config.{js,ts}`; or `vite.config.*` with `@vitejs/plugin-vue` | **Vue** | `${CLAUDE_PLUGIN_ROOT}/context/panels/vue.md` |
| `svelte` or `@sveltejs/kit` in `package.json`; `**/*.svelte` files; `svelte.config.{js,ts}`; or routes under `src/routes/**` matching SvelteKit conventions | **Svelte** | `${CLAUDE_PLUGIN_ROOT}/context/panels/svelte.md` |
| `solid-js` or `@solidjs/start` in `package.json`; `**/*.{jsx,tsx}` with Solid imports (`createSignal`, `createEffect`, etc.); `vite.config.*` with `vite-plugin-solid`; or `app.config.{js,ts}` (SolidStart) | **SolidJS** | `${CLAUDE_PLUGIN_ROOT}/context/panels/solid.md` |
| `**/*.go`, `go.mod`, `go.sum` | **Go** | `${CLAUDE_PLUGIN_ROOT}/context/panels/go.md` |
| `**/*.rs`, `Cargo.toml`, `Cargo.lock` | **Rust** | `${CLAUDE_PLUGIN_ROOT}/context/panels/rust.md` |
| `**/*.java`, `**/*.kt`, `**/*.kts`, `pom.xml`, `build.gradle*`, `settings.gradle*` | **JVM** | `${CLAUDE_PLUGIN_ROOT}/context/panels/jvm.md` |
| `**/*.{c,h,cpp,cc,cxx,hpp,hh}`, `CMakeLists.txt`, `*.cmake` | **C/C++** | `${CLAUDE_PLUGIN_ROOT}/context/panels/cpp.md` |
| `**/*.{sh,bash,zsh}`, files with a shell shebang, `.git/hooks/*`, `.husky/*`, shell snippets inside Makefiles/Dockerfiles/CI YAML | **Shell** | `${CLAUDE_PLUGIN_ROOT}/context/panels/shell.md` |
| Files whose path contains `route`, `handler`, `controller`, `endpoint`, `view`, `api`, or `resources`; `**/*.go` with HTTP patterns; OpenAPI / AsyncAPI / Swagger specs (`openapi.{yaml,json}`, `swagger.{yaml,json}`); or `app/routes/**` | **HTTP/API** | `${CLAUDE_PLUGIN_ROOT}/context/panels/http-api.md` |
| HTMX is present in the project: `htmx` in a dependency manifest (`package.json`, `requirements.txt`, `pyproject.toml`, `Gemfile`), `hx-*` attributes in template files in scope, or `htmx-ext-*` files in scope | **Hypermedia** | `${CLAUDE_PLUGIN_ROOT}/context/panels/hypermedia.md` |
| OAuth / OIDC code (`oauth`, `openid`, `passport`, `authlib`, `auth.js`, `next-auth`, `@auth0/`, `lucia`, `keycloak`, `hydra`, IdentityServer); JWT libraries (`jsonwebtoken`, `jose`, `pyjwt`, `JJWT`); session management (`express-session`, `iron-session`, `flask-login`, `django.contrib.auth`); password hashing (`bcrypt`, `argon2`, `scrypt`, `passlib`); WebAuthn (`@simplewebauthn`, `py_webauthn`); authorization libraries (`oso`, `casbin`, `cerbos`, `opa`); SAML clients; routes matching `/login`, `/logout`, `/oauth/**`, `/token`, `/authorize`, `/userinfo`, `/.well-known/**` | **Identity** | `${CLAUDE_PLUGIN_ROOT}/context/panels/identity.md` |
| Files importing cryptographic libraries — Python (`cryptography`, `pycryptodome`, `nacl`, `hmac`, `secrets`), Node (`crypto`, `noble-*`, `tweetnacl`, `libsodium-wrappers`), Go (`crypto/*`, `golang.org/x/crypto`, `filippo.io/age`), Java/Kotlin (`javax.crypto`, `java.security`, `BouncyCastle`, `Tink`), Rust (`ring`, `rustls`, `aes-gcm`, `chacha20poly1305`, `sodiumoxide`), Swift (`CryptoKit`); password-hash libraries (`bcrypt`, `argon2`, `scrypt`); TLS configuration code; signing / verification / encryption-at-rest code | **Cryptography** | `${CLAUDE_PLUGIN_ROOT}/context/panels/cryptography.md` |
| `**/*.html`, `**/*.css`, `**/*.scss`, `**/*.jsx`, `**/*.tsx`, or files under `static/`, `public/`, or `templates/` | **UI** | `${CLAUDE_PLUGIN_ROOT}/context/panels/ui.md` |
| `@uswds/uswds` in a dependency manifest; `usa-*` classes in markup in scope; USWDS Sass entry points (`_uswds-theme*.scss`, `uswds-init.scss`); or files under `uswds*/` | **USWDS** | `${CLAUDE_PLUGIN_ROOT}/context/panels/uswds.md` |
| Files importing LLM clients (`anthropic`, `openai`, `langchain`, `litellm`, `instructor`, `vercel/ai`, `langgraph`, `llama_index`, Bedrock / Vertex SDK calls); prompt template / system-prompt files; embedding / vector-store reads or writes (`pinecone`, `qdrant`, `weaviate`, `chroma`, `pgvector`); RAG pipelines; agent loops or tool-calling handlers; LLM evaluation harnesses or eval datasets | **AI/LLM** | `${CLAUDE_PLUGIN_ROOT}/context/panels/ai-llm.md` |
| `.github/workflows/**`, `.gitlab-ci.yml`, `Jenkinsfile`, `Dockerfile*`, `Makefile`, `.pre-commit-config.yaml`, or dependency lockfiles | **CI/CD** | `${CLAUDE_PLUGIN_ROOT}/context/panels/cicd.md` |
| `**/migrations/**`, `**/*.sql`, `**/schema.{rb,prisma,sql}`, ORM model files, or files constructing raw queries | **Database** | `${CLAUDE_PLUGIN_ROOT}/context/panels/database.md` |
| Airflow (`dags/**/*.py`, `airflow.cfg`, files with `@dag`/`DAG(...)`); Dagster (`@asset`, `@op`, `Definitions`, `dagster.yaml`); Prefect (`@flow`, `@task`); dbt (`dbt_project.yml`, `models/**/*.sql`, `**/schema.yml`, `snapshots/`, `macros/`); Spark / PySpark / Beam pipelines; warehouse SQL (BigQuery, Snowflake, Redshift, Databricks); ML training/serving code (`scikit-learn`, `xgboost`, `torch`, `tensorflow`, `mlflow`, feature stores like Feast/Tecton) | **Data Engineering** | `${CLAUDE_PLUGIN_ROOT}/context/panels/data-engineering.md` |
| `**/*.tf`, `**/*.tfvars`, K8s manifests (`apiVersion:`/`kind:`), Helm charts, CDK/Pulumi, Ansible, CloudFormation | **Infrastructure** | `${CLAUDE_PLUGIN_ROOT}/context/panels/infrastructure.md` |
| `**/tests/**`, `**/__tests__/**`, `**/*_test.*`, `**/*.test.*`, `**/*.spec.*`, `conftest.py`, test runner configs | **Testing** | `${CLAUDE_PLUGIN_ROOT}/context/panels/testing.md` |
| Service entry points, request handlers, jobs, queue consumers, or files configuring telemetry (otel, logging, Prometheus) | **Observability** | `${CLAUDE_PLUGIN_ROOT}/context/panels/observability.md` |
| Hot-path code (request handlers, loops over user-scaled collections, batch jobs, render loops), benchmarks, profiler output | **Performance** | `${CLAUDE_PLUGIN_ROOT}/context/panels/performance.md` |
| Service-to-service code: queue producers/consumers, RPC/HTTP clients to owned services, webhook handlers, retry/idempotency/saga logic | **Distributed** | `${CLAUDE_PLUGIN_ROOT}/context/panels/distributed.md` |

Panels are additive. Examples:
- A route handler in Python activates Core + Python + HTTP/API (+ Observability if it logs).
- A Python route handler returning an HTMX swap activates Core + Python + HTTP/API + Hypermedia + UI (+ USWDS if `usa-*` classes appear in the rendered template).
- An `/oauth/callback` handler activates Core + (lang) + HTTP/API + Identity. A `/login` route that hashes a password and sets a session cookie activates Core + (lang) + HTTP/API + Identity + Cryptography (the password-hash construction). A JWT verification middleware in Express activates Core + TypeScript/JS + Identity + Cryptography.
- A file calling `crypto.createCipheriv('aes-256-gcm', ...)` or `cryptography.fernet.Fernet(...)` activates Core + (lang) + Cryptography.
- A TSX component activates Core + TypeScript/JS + UI.
- A TSX component in a React project activates Core + TypeScript/JS + React + UI (+ HTTP/API if it's a route handler in Next.js / Remix; + AI/LLM if it calls an LLM client).
- An Angular component (`*.component.ts` + template) activates Core + TypeScript/JS + Angular + UI.
- A Vue SFC (`*.vue`) activates Core + TypeScript/JS + Vue + UI.
- A Svelte route file (`+page.svelte` + `+page.server.ts`) activates Core + TypeScript/JS + Svelte + UI (+ HTTP/API for `+server.ts` endpoints, + Database if the server load queries directly).
- A SQL migration activates Core + Database.
- A `.github/workflows/deploy.yml` activates Core + CI/CD.
- A Terraform module activates Core + Infrastructure.
- A Go queue consumer activates Core + Go + Distributed (+ Observability).
- A Python service calling an LLM activates Core + Python + AI/LLM (+ Observability).
- A dbt model file activates Core + Database + Data Engineering. An Airflow DAG (`dags/foo.py`) activates Core + Python + Data Engineering (+ Observability). A PyTorch training script reading from Snowflake activates Core + Python + Database + Data Engineering.

When HTTP/API and Hypermedia both activate, defer generic HTTP design questions (REST constraints, status code policy across the API, versioning, OpenAPI discipline) to HTTP/API and reserve Hypermedia for partial-response semantics (HX-* headers, swap fragments, SSE event naming, HX-Redirect vs. PRG). When UI and USWDS both activate, defer generic progressive-enhancement / accessibility / Tailwind-discipline findings to UI and reserve USWDS for the design-system boundary rules (canonical-component usage, mixing-system patterns, HTMX-USWDS bridge re-init).

When more than five panels activate on a single review, prioritize findings by severity across all panels rather than producing exhaustive findings per panel.

---

## Step 2: Load Panel Definitions

Read only the panel files for active panels. Core is always active. Do not read panel files for inactive panels.

The Secondary panel (`${CLAUDE_PLUGIN_ROOT}/context/panels/secondary.md`) is loaded on demand — only when the primary panels reach a genuine impasse synthesis cannot resolve.

---

## Target

```
$ARGUMENTS
```

If `$ARGUMENTS` is empty, review all changed files (`git diff --name-only`). If a specific file or glob is given, review those files. Read every file in scope before writing a single finding.

---

## Step 3: Conduct the Review

After loading active panel files and reading all files in scope, produce findings across every dimension defined in the loaded panels.

---

## Output Format

Write the critique as a structured report. Do not write anything until you have read all target files. After producing the report, write it to `CRITIQUE.md` in the current working directory.

```
═══════════════════════════════════════════════════════
  EXPERT CODE CRITIQUE
  Target: [file(s) reviewed]
  Active panels: [Core | + Python | + TypeScript/JS | + Angular | + React | + Vue | + Svelte | + SolidJS | + Go | + Rust | + JVM | + C/C++ | + Shell | + HTTP/API | + Hypermedia | + Identity | + Cryptography | + UI | + USWDS | + AI/LLM | + CI/CD | + Database | + Data Engineering | + Infrastructure | + Testing | + Observability | + Performance | + Distributed]
  Date: [today's date]
═══════════════════════════════════════════════════════

## Summary

[3–5 sentences. Overall assessment. Primary strengths. Primary concerns. Gestalt only — no findings listed here.]

## Finding Table

| ID | Severity | Dimension | Panel | Location | Finding |
|----|----------|-----------|-------|----------|---------|
| C-01 | BLOCKER/MAJOR/MINOR/OBS | [dimension] | [panel] | file:line | [one-line description] |

Severity guide:
- BLOCKER: Serious design problem likely to cause bugs, maintenance failure, or security issues. Must be resolved before shipping.
- MAJOR: Clear violation of a principle with meaningful consequences. Fix before merge.
- MINOR: Improvement opportunity. Fix if the code is being touched anyway.
- OBS: Observation worth noting. May reflect a legitimate tradeoff.

## Detailed Findings

For each finding:

### C-XX: [Short Title]
**Severity:** [BLOCKER/MAJOR/MINOR/OBS]
**Dimension:** [dimension name]
**Panel:** [which panel raised this]
**Location:** `file:line`

**What I see:**
[Describe the specific code — quote or describe what is actually there.]

**Expert Perspective:**
[Which expert(s) flag this? If experts disagree, name the disagreement explicitly.]

**Synthesis:**
[What should be done, and why? If a genuine tradeoff, say so.]

**Suggested direction:**
[Concrete, specific recommendation. Not "consider refactoring" — say what to extract, rename, remove, or add.]

---

## Codebase Patterns

*This section looks beyond the changed files. What does this change reveal about habits, patterns, or systemic tendencies in the broader codebase?*

For each observation:

### P-XX: [Short Title]
**Type:** [Recurring pattern / Systemic gap / Positive pattern worth continuing]
**Where it appears:** [list of files/modules — not just the ones in scope]

[2–4 sentences describing the pattern, whether it's a problem, and what the systemic fix would be.]

---

## Highlights

[2–4 things the code does well. Be specific — name the exact pattern or decision and why it reflects good practice.]

## Verdict

**Recommended action:** [APPROVE / REVISE / MAJOR REWORK]
**Blocker count:** [N]
**Major count:** [N]
**Summary:** [One sentence on what must happen before this code is production-ready.]
```

---

## Conduct Rules

1. **Be specific.** Every finding must reference a file and line (or method/class name). No finding based on general impression.
2. **Cite the code.** Quote or precisely describe what you observed — do not paraphrase vaguely.
3. **Acknowledge tradeoffs.** If two experts disagree, name the disagreement. The user deserves to understand the actual debate, not a false consensus.
4. **Do not over-decompose.** Resist the urge to flag every function as too long. Apply Ousterhout's depth test before flagging.
5. **Do not generate code.** Surface findings and directions. Describe the refactoring precisely. Do not write replacement code unless asked.
6. **No padding.** Every finding must justify its severity. Do not flag MAJOR issues that are OBS-level.
7. **Prioritize by impact.** BLOCKERs first. If there are more than 10 findings, group MINOR/OBS findings into a summary table.
8. **Security flaws are BLOCKERs unconditionally.** A design-level security flaw (wrong trust boundary, missing authorization layer, user input reaching a subprocess) blocks shipment. Do not downgrade.
9. **Architectural prompt injection is a BLOCKER.** External, attacker-influenced content reaching an LLM context window while the model has write-capable tools available, with no documented mitigation, is a design-level flaw.
10. **Codebase Patterns are not findings.** They are observations about the broader codebase surfaced by this change. They do not count toward the blocker/major totals and do not affect the Verdict — they inform the next design or refactoring session.

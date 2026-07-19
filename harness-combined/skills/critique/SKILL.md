---
name: critique
description: Apply domain-specialist panels to a chosen scope — Python idioms, HTTP/API design, UI patterns, AI/LLM security — each with a distinct mental model, not just a harder general scan. Scope is set by argument (files, globs, a git ref/range, or a scope keyword); when no argument is given the command ASKS which scope to run against, defaulting to the whole codebase focused on changes since the last critique — it does not silently assume uncommitted changes. Also produces a Codebase Patterns section that looks beyond the changed files to surface systemic habits. TRIGGER when the user wants a specific expert lens applied to a change, names a domain ("security review", "Python idioms", "what would an API designer say"), or asks for panel review (e.g. "critique the auth route", "panel review of the new handler", "what's wrong with this from an API design perspective"). SKIP for ticket-scoped post-build reviews (use the review skill, which reads problem/requirements/solution as baseline), for general correctness or style checks (use /code-review), and when the user only wants lint output (use /gate).
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
| `**/*.graphql`, `**/*.gql`, `schema.graphql` / SDL files; `graphql`, `@apollo/*`, `apollo-server`, `graphql-yoga`, `relay`, `type-graphql`, `strawberry-graphql`, `ariadne`, or `gqlgen` in a dependency manifest; resolver maps / schema-first or code-first server definitions | **GraphQL** | `${CLAUDE_PLUGIN_ROOT}/context/panels/graphql.md` |
| `**/*.proto`; `grpc`, `@grpc/grpc-js`, `grpcio`, `google.golang.org/grpc`, `tonic`, or `grpc-java` in a dependency manifest; generated stubs (`*_pb2.py`, `*.pb.go`, `*_pb.ts`, `*_grpc.rb`); `buf.yaml` / `buf.gen.yaml` | **gRPC/Protobuf** | `${CLAUDE_PLUGIN_ROOT}/context/panels/grpc-protobuf.md` |
| `**/*.cs`, `**/*.csproj`, `**/*.sln`, `**/*.fs`, `**/*.fsproj`, `**/*.vb`, `**/*.vbproj`; `Directory.Build.props`, `global.json`, `packages.config`, or `*.nuspec` in scope | **.NET** | `${CLAUDE_PLUGIN_ROOT}/context/panels/dotnet.md` |
| HTMX is present in the project: `htmx` in a dependency manifest (`package.json`, `requirements.txt`, `pyproject.toml`, `Gemfile`), `hx-*` attributes in template files in scope, `hx-*` attributes in *string literals* inside files in scope (e.g., `render_template_string`, inline JSX templates, server-side HTML strings), or `htmx-ext-*` files in scope | **Hypermedia** | `${CLAUDE_PLUGIN_ROOT}/context/panels/hypermedia.md` |
| OAuth / OIDC code (`oauth`, `openid`, `passport`, `authlib`, `auth.js`, `next-auth`, `@auth0/`, `lucia`, `keycloak`, `hydra`, IdentityServer); JWT libraries (`jsonwebtoken`, `jose`, `pyjwt`, `JJWT`); session management (`express-session`, `iron-session`, `flask-login`, `django.contrib.auth`); password hashing (`bcrypt`, `argon2`, `scrypt`, `passlib`); WebAuthn (`@simplewebauthn`, `py_webauthn`); authorization libraries (`oso`, `casbin`, `cerbos`, `opa`); SAML clients; routes matching `/login`, `/logout`, `/oauth/**`, `/token`, `/authorize`, `/userinfo`, `/.well-known/**` | **Identity** | `${CLAUDE_PLUGIN_ROOT}/context/panels/identity.md` |
| Files importing cryptographic libraries — Python (`cryptography`, `pycryptodome`, `nacl`, `hmac`, `secrets`), Node (`crypto`, `noble-*`, `tweetnacl`, `libsodium-wrappers`), Go (`crypto/*`, `golang.org/x/crypto`, `filippo.io/age`), Java/Kotlin (`javax.crypto`, `java.security`, `BouncyCastle`, `Tink`), Rust (`ring`, `rustls`, `aes-gcm`, `chacha20poly1305`, `sodiumoxide`), Swift (`CryptoKit`); password-hash libraries (`bcrypt`, `argon2`, `scrypt`); TLS configuration code; signing / verification / encryption-at-rest code | **Cryptography** | `${CLAUDE_PLUGIN_ROOT}/context/panels/cryptography.md` |
| `**/*.html`, `**/*.css`, `**/*.scss`, `**/*.jsx`, `**/*.tsx`, files under `static/`, `public/`, or `templates/`, or HTML markup inside string literals in any file in scope (e.g., `render_template_string` in Flask, inline templates in server-side handlers, JSX template literals) | **UI** | `${CLAUDE_PLUGIN_ROOT}/context/panels/ui.md` |
| `@uswds/uswds` in a dependency manifest; `usa-*` classes anywhere in markup or string literals in scope (including inline templates inside server-side files); USWDS Sass entry points (`_uswds-theme*.scss`, `uswds-init.scss`); or files under `uswds*/` | **USWDS** | `${CLAUDE_PLUGIN_ROOT}/context/panels/uswds.md` |
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
- A GraphQL resolver in a Node/TypeScript project activates Core + TypeScript/JS + GraphQL (+ HTTP/API if exposed over HTTP; + Database if resolvers query directly). A `schema.graphql` alone activates Core + GraphQL.
- A `.proto` service definition activates Core + gRPC/Protobuf. A Go gRPC server implementation activates Core + Go + gRPC/Protobuf + Distributed (+ Observability); a Python gRPC service activates Core + Python + gRPC/Protobuf + Distributed.
- A C# ASP.NET Core controller activates Core + .NET + HTTP/API (+ Database if it uses EF Core). A `.csproj` or `global.json` alone activates Core + .NET.
- A Python service calling an LLM activates Core + Python + AI/LLM (+ Observability).
- A dbt model file activates Core + Database + Data Engineering. An Airflow DAG (`dags/foo.py`) activates Core + Python + Data Engineering (+ Observability). A PyTorch training script reading from Snowflake activates Core + Python + Database + Data Engineering.

When HTTP/API and Hypermedia both activate, defer generic HTTP design questions (REST constraints, status code policy across the API, versioning, OpenAPI discipline) to HTTP/API and reserve Hypermedia for partial-response semantics (HX-* headers, swap fragments, SSE event naming, HX-Redirect vs. PRG). When UI and USWDS both activate, defer generic progressive-enhancement / accessibility / Tailwind-discipline findings to UI and reserve USWDS for the design-system boundary rules (canonical-component usage, mixing-system patterns, HTMX-USWDS bridge re-init).

When more than five panels activate on a single review, prioritize findings by severity across all panels rather than producing exhaustive findings per panel.

**Inline-content rule.** Triggers describing markup, attributes, or class patterns ("`hx-*` attributes," "`usa-*` classes," HTML/CSS) apply to *string literals inside files in scope*, not only to files whose extension matches a template type. A Python route handler that calls `render_template_string('<div hx-swap-oob...>')` activates Hypermedia, UI, and (if applicable) USWDS in addition to the language and HTTP/API panels — the inline markup is the contract surface the panel reviews. Do not require markup to live in a `.html` file for the markup-aware panels to apply.

**Considered-and-deferred panels.** When a panel is *almost* activated but the trigger is ambiguous (e.g., an inline-content pattern that appears only in a comment, or a single match in a test fixture), record it as deferred rather than silently dropping it. The report header has a "Panels considered, deferred" line for this — see Output Format below.

**Design-artifact mode.** When the files in scope are design artifacts — `problem.md`, `requirements.md`, `solution.md`, README-style design docs, RFCs, ADRs (architectural decision records) — treat this as a *design review* rather than a code review. Typical invocation: `/critique problem.md requirements.md solution.md`. Infer the intended file scope from the artifacts' content — what languages, frameworks, integration points, identity layers, data systems, or LLM tooling the design proposes touching — and apply the trigger table against that inferred scope. The same panel set fires; the lens is "is this design going to produce code that respects the panel's hazards?" rather than "does this code respect them?". Findings reference the artifact section (e.g., `solution.md § Auth flow`) rather than `file:line`. The Fix section names the design correction (e.g., "rework the auth section to specify Argon2id rather than 'a password hash'") rather than a code edit.

The critic agent (`${CLAUDE_PLUGIN_ROOT}/agents/critic.md`) runs in design-mode automatically during `/problem` Phase 5; use `/critique` against design artifacts when you want a comprehensive on-demand review outside the SDLC pipeline — for example, against an existing project's design docs, against an RFC before it gets ticketed, or against a solution.md you want to re-evaluate after the original critic round.

---

## Step 2: Load Panel Definitions

Read only the panel files for active panels. Core is always active. Do not read panel files for inactive panels.

The Secondary panel (`${CLAUDE_PLUGIN_ROOT}/context/panels/secondary.md`) is loaded on demand — only when the primary panels reach a genuine impasse synthesis cannot resolve.

---

## Scope

```
$ARGUMENTS
```

Resolve the review scope **before** reading any code. Do not assume uncommitted changes.

- **`$ARGUMENTS` names files or globs** (e.g. `src/auth.py`, `web/**/*.svelte`, `problem.md requirements.md`) → review exactly those files. No prompt.
- **`$ARGUMENTS` is a git ref or range** (e.g. `main..HEAD`, a branch name, a commit SHA) → review the files that ref/range touches (`git diff --name-only <range>`). No prompt.
- **`$ARGUMENTS` is a scope keyword** → resolve it, no prompt:
  - `codebase` / `all` → every tracked file (`git ls-files`).
  - `uncommitted` / `working` → `git diff --name-only HEAD` plus untracked files.
  - `since-last-critique` → the whole codebase focused on the diff since the last critique (see **Resolving "since last critique"** below).
- **`$ARGUMENTS` is empty** → **ask the user** which scope to run against with the `AskUserQuestion` tool. Offer these options (first is the default/recommended); do not read code until answered:
  1. **Since last critique (recommended)** — the whole codebase as context, findings focused on what changed since the previous critique.
  2. **Uncommitted changes** — `git diff` + untracked files only.
  3. **Entire codebase** — every tracked file, no change-focus.
  4. **Specific files or ref** — the user names a path, glob, or git range (route their answer through the rules above).

**Resolving "since last critique".** The scope's *context* is the whole codebase — panel activation and the Codebase Patterns section see everything — while the *focus* (the files that receive "this change" findings) is the diff since the previous critique:

1. Find the previous critique's anchor: scan `.harness/critiques/` (resolved at the main project root, never inside a worktree — see Output Format) for the newest report and read its `Base commit:` header line.
2. The focused file set is `git diff --name-only <base>..HEAD` plus current uncommitted and untracked changes.
3. If no prior report exists or none records a `Base commit:` (first run, or legacy reports), fall back to reviewing every tracked file and note in the report's Summary that no prior critique anchor was found, so this run establishes the baseline.

Read every file in the focused set — and enough of the surrounding codebase to activate the right panels and surface Codebase Patterns — before writing a single finding.

---

## Step 3: Conduct the Review

After loading active panel files and reading all files in scope, produce findings across every dimension defined in the loaded panels.

---

## Output Format

Write the critique as a structured report. Do not write anything until you have read all target files. After producing the report, write it to the harness critiques directory — **never** to `CRITIQUE.md` in the current working directory, and **never** inside a worktree.

**Report destination.** Write the report to `.harness/critiques/<report-file>`, creating the `.harness/critiques/` directory if it does not exist. This sits beside `.harness/results/` and `.harness/memory.db` in the harness state home, so it inherits the same git-ignore treatment and never leaks into delivered code.

- **Resolve `.harness/` at the main project root, never inside a worktree.** If the current directory is inside a `.worktrees/<slug>/` checkout (a ticket worktree), do **not** write the report there — a report committed into a worktree would be swept into the delivery squash. Resolve the main working tree's root (e.g. the directory holding `.tickets/` and `.harness/`; from within a worktree, the parent of `git rev-parse --git-common-dir`) and write the report to *its* `.harness/critiques/`.
- **Filename: `<YYYY-MM-DD>-<NN>-<target-slug>.md`.** The date leads the filename so a plain reverse-lexical sort of the reports is globally newest-first **regardless of target** — put the date first, not the slug, or reports for different targets interleave by name instead of by time. `<YYYY-MM-DD>` is today's date. `<NN>` is a two-digit counter (`01`, `02`, …): scan `.harness/critiques/` for existing `<YYYY-MM-DD>-*.md` files (any target) and use the next unused value, so same-day re-runs never collide. `<target-slug>` is a short kebab-case slug of the review target (the file/glob in `$ARGUMENTS`, or the resolved scope when none was given — `since-last-critique`, `uncommitted`, or `codebase`). This makes filenames sort chronologically and collision-free across same-day re-runs, so successive critiques never overwrite each other. Call this resolved path `<report-path>` below.

**Base-commit anchor.** The report header's `Base commit:` line is machine-read: the `since-last-critique` scope resolves the previous anchor by reading the newest report's `Base commit:` (see Scope). Always emit it — a report without it cannot anchor the next incremental critique, forcing a full-codebase fallback. Record `git rev-parse HEAD` at the time the review is conducted.

**Ticket-pointer rule.** When the critique's target files belong to a ticket — a path inside a ticket worktree (`.worktrees/<slug>/…`) or inside a ticket directory (`.tickets/<slug>/…`) — append a one-line pointer to that ticket's `critic-findings.md` (the durable per-ticket findings index; see "Critic findings file" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`), so the report is discoverable from the ticket later. The line carries four fields — date, target, verdict, and report path:

```
- <YYYY-MM-DD> · critique · target: <target> · verdict: <APPROVE|REVISE|MAJOR REWORK> · report: <report-path>
```

`<verdict>` is the **Recommended action** from the report's Verdict section. Append under a `## Critique pointers` heading (create it if absent); do not overwrite existing content. When the target does not belong to any ticket, skip this step.

**Inline PR comments (opt-in, `--comment`).** When the operator invokes the skill with `--comment`, additionally post the findings as inline GitHub PR review comments after writing `<report-path>`; the default (no flag) is the written report only. Read the findings back from the **exact `<report-path>` resolved and written above** — the main-root-anchored absolute path — and do **not** re-derive `.harness/critiques/` relative to the current directory, which would point at the wrong `.harness/` when invoked from inside a worktree. Parse the report's findings with `parse_critic_findings` and hand them to `post_findings(..., kind="critic")`:

```python
from pathlib import Path
from gates.critic_finding_parser import parse_critic_findings
from gates.pr_commenter import post_findings, format_summary

report_path = Path(report_path)  # the absolute <report-path> resolved + written above; NOT re-derived from cwd
findings = parse_critic_findings(report_path.read_text(), Path("."))
result = post_findings(findings, Path("."), should_post=True, kind="critic", cwd=Path("."))
print(format_summary(result))
```

BLOCKER and MAJOR findings become inline review comments on their `file:line`; MINOR and OBS become COMMENT-type inline comments whose body is prefixed `[suggestion]` (they do **not** use GitHub's code-suggestion markdown). Findings without a `file:line` post as top-level PR comments. `post_findings` deduplicates against existing comments (critic key: `file:line:severity:code`, stable across re-renders) and submits everything in one batched `gh api .../reviews` call, falling back to terminal-only output — with a specific reason — when `gh` is unavailable/unauthenticated, no open PR exists, or the dedup fetch fails. Without `--comment`, do not post.

The report is structured for a reader who *skims first, dives second*. Verdict comes before findings so the reader knows whether to read on; the Finding Table is the punch list; BLOCKER/MAJOR Detail is the substantive read; MINOR/OBS findings stay in tabular form because the table row already says what's needed. Two-paragraph synthesis on a MINOR-severity stylistic note does not pull its weight.

```
═══════════════════════════════════════════════════════
  EXPERT CODE CRITIQUE
  Target: [file(s) reviewed]
  Active panels: [Core | + Python | + TypeScript/JS | + Angular | + React | + Vue | + Svelte | + SolidJS | + Go | + Rust | + JVM | + C/C++ | + Shell | + HTTP/API | + Hypermedia | + Identity | + Cryptography | + UI | + USWDS | + AI/LLM | + CI/CD | + Database | + Data Engineering | + Infrastructure | + Testing | + Observability | + Performance | + Distributed]
  Panels considered, deferred: [list of panels whose triggers were ambiguous, with one-line reason each — or "none"]
  Scope: [how scope was resolved — e.g. "since last critique (<base>..HEAD)", "uncommitted", "codebase", or the files/glob/ref given]
  Date: [today's date]
  Base commit: [`git rev-parse HEAD` at review time — the anchor a later "since last critique" run diffs from]
═══════════════════════════════════════════════════════

## Verdict

**Recommended action:** [APPROVE / REVISE / MAJOR REWORK]
**Counts:** [N] BLOCKER · [N] MAJOR · [N] MINOR · [N] OBS
**What must change to ship:** [One sentence naming the highest-leverage required fix(es). If there are zero blockers, "Approved as-is" or "Approved with N major cleanups recommended."]

## Summary

[3–5 sentences. Overall assessment. Primary strengths. Primary concerns. Gestalt only — no finding IDs listed here.]

## Finding Table

Sort by severity (BLOCKER → MAJOR → MINOR → OBS), then by impact within severity.

| ID | Severity | Panel | Dimension | Location | Finding |
|----|----------|-------|-----------|----------|---------|
| C-01 | BLOCKER | [panel] | [dimension] | `file:line` | [one-line description] |

Severity guide:
- **BLOCKER**: Serious design problem likely to cause bugs, maintenance failure, or security issues. Must be resolved before shipping.
- **MAJOR**: Clear violation of a principle with meaningful consequences. Fix before merge.
- **MINOR**: Improvement opportunity. Fix if the code is being touched anyway.
- **OBS**: Observation worth noting. May reflect a legitimate tradeoff.

## BLOCKER & MAJOR Detail

For each BLOCKER and MAJOR finding only (MINOR / OBS stay in the Finding Table above — their one-line description is the finding). Compact format:

### C-XX: [Short Title]
**[BLOCKER | MAJOR]** · [Panel] · [Dimension] · `file:line`

[2–4 sentences. Describe what is in the code, name the expert(s) whose lens flags it, and explain why it's wrong. If experts disagree, name the disagreement in one sentence. Combine "what I see" and "expert perspective" into prose, not separate subsections.]

**Fix:** [Concrete recommendation in 1–3 sentences. Name the specific library, function, parameter, or refactor. For single-line edits, quote the change. Not "consider refactoring" — say what to extract, rename, remove, or add.]

---

## MINOR & OBS

[Either: leave this section empty and note "(See Finding Table — MINOR and OBS findings need no further detail.)" if all MINOR/OBS rows are self-explanatory.]

[Or: if a MINOR/OBS row needs one sentence of context the table can't carry, list as a bulleted line:]

- **C-XX** (`file:line`): [One sentence of additional context — why this matters or what the fix is. No expanded format.]

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

[2–4 things the code does well. Be specific — name the exact pattern or decision and why it reflects good practice. Skip this section if there's nothing genuinely worth highlighting; don't pad to balance the negatives.]
```

**Per-file grouping for multi-file reviews.** When more than five files are in scope, group the BLOCKER & MAJOR Detail section by file rather than by finding ID. Findings within each file group still use the compact `C-XX` format; the grouping is a reader affordance for scoping remediation to one file at a time.

**Size discipline.** A critique on a single 100-line file should produce ~200–300 lines of report. A 1000-line multi-file diff should produce 600–1000 lines, not 6000. If the report exceeds 3× the source line count, the Detail section is over-elaborating — tighten the per-finding prose, not the finding count.

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
11. **Split independent BLOCKERs and MAJORs; bundle only what shares a single fix.** If two issues at the same severity have different remediation steps (different file edits, different libraries, different conceptual changes), they are separate findings even when thematically related — "no CSRF protection," "no JWT expiry," "no MFA path," "no login rate limit" are four findings, not one. Bundle only when *one* fix addresses both (e.g., "missing HTTP security headers" naming three at once is acceptable because one config block adds all three). The risk of bundling independent issues is that the lower-severity ones in the bundle become invisible during remediation — they get scoped out, deferred, or forgotten.

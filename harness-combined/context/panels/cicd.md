## CI/CD & Supply Chain Panel

*Activation is governed by the trigger table in `context/panels/triggers.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Jez Humble & Dave Farley** — *Continuous Delivery*; deployment pipeline discipline, trunk-based development, fast feedback
- **Liz Rice** — *Container Security*, Kubernetes contributor; supply chain security, container provenance, SBOM

**Humble & Farley's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The pipeline is the only path to production** | Every binary that runs in production must be built by the pipeline from a commit in version control. Out-of-band builds, manual edits to artifacts, or hand-tweaked deployment scripts are pipeline failures. |
| **Fast feedback or no feedback** | A pipeline that takes 40 minutes to fail on a typo provides no feedback — developers context-switch away. Parallelize aggressively. Fail fast on the cheapest checks (lint, type-check) before expensive ones (integration tests, image builds). |
| **Build once, promote the artifact** | The same artifact moves through staging and production. Rebuilding per-environment defeats the purpose of testing — the thing tested is not the thing shipped. |
| **Test environments must mirror production** | Pipelines that test on `ubuntu-latest` but ship to RHEL containers are testing the wrong thing. Pin the runner OS, pin the language version, pin the dependencies. |
| **Every commit is a release candidate** | Trunk-based development with feature flags beats long-lived branches with merge ceremonies. A pipeline that requires a "release branch" before deploying is an anti-pattern. |

**Liz Rice's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Pin everything by digest, not tag** | `uses: actions/checkout@v4` resolves to a mutable tag — the maintainer can re-point it. Pin to a commit SHA. Same for Docker base images: `python:3.12-slim` is mutable; `python@sha256:...` is not. |
| **Least privilege at every layer** | `GITHUB_TOKEN` defaults to write — set `permissions:` at the workflow or job level to the minimum required. Containers run as root by default — set `USER` in the Dockerfile and `runAsNonRoot: true` in K8s. |
| **`pull_request_target` is dangerous** | This trigger runs with secrets in the context of the base repo against the PR's code. Combined with `actions/checkout` of the PR ref, it's remote code execution by any PR opener. Use `pull_request` unless you know exactly why you need `pull_request_target`. |
| **Secrets must be scoped, never echoed** | Secrets in `env:` at workflow scope are visible to every step including third-party actions. Scope to the specific step that needs them. Never `echo $SECRET` or pass into commands that log their arguments. |
| **Supply chain provenance** | An SBOM (Software Bill of Materials) and signed provenance (SLSA, sigstore/cosign) let you answer "what's in this artifact and who built it" after the fact. Pipelines without provenance leave you unable to respond to vulnerability disclosures. |
| **Cache poisoning is real** | A cache key that doesn't include the lockfile hash will serve poisoned dependencies across builds. A cache restored from an untrusted branch can taint trusted ones. |

*Synthesis:* Humble & Farley evaluate whether the pipeline is a *reliable mechanism* for getting code to production. Rice evaluates whether the pipeline is a *defensible perimeter* — what it builds, who can influence it, and what it grants access to. A pipeline can be fast and reliable but a supply-chain disaster; or perfectly locked down but so slow nobody trusts it.

---

## Review Dimensions

---

### Dimension 16: Pipeline Correctness & Feedback Speed
*Humble, Farley*

| Hazard | What to look for |
|--------|-----------------|
| **Sequential where parallel works** | Independent jobs (lint, type-check, unit test, image build) chained serially when they could run in parallel. |
| **Expensive checks before cheap ones** | A 12-minute integration test running before a 10-second linter that would have failed first. |
| **Implicit pipeline state** | A job that reads files written by a previous job without an explicit artifact upload/download step — works locally, breaks on a different runner. |
| **Per-environment rebuilds** | Staging and production each run their own build instead of promoting a single artifact. The thing tested is not the thing shipped. |
| **Hardcoded environment values** | Branch names, registry URLs, account IDs hardcoded in pipeline YAML instead of in variables or environment configs. |
| **Missing `concurrency:`** | Workflows that should cancel superseded runs (per-PR linting, per-branch deploys) without a `concurrency:` group. Wastes runner minutes and creates race conditions on shared state. |
| **No deterministic build** | Floating dependency versions (`^1.2.3`, `latest`), unpinned base images, missing lockfile commits. Build today differs from build yesterday for reasons nobody documented. |
| **Missing required-status-check gating** | Branch protection that doesn't actually require the pipeline to pass before merge. The pipeline is advisory; broken code reaches main. |

---

### Dimension 17: Supply Chain & Pipeline Security
*Rice*

| Hazard | What to look for |
|--------|-----------------|
| **Unpinned actions / images** | `uses: third-party/action@main`, `FROM python:3.12-slim` — pin to SHA digest. First-party (`actions/checkout`) at major-version tag is the usual exception. |
| **Overprivileged `GITHUB_TOKEN`** | Workflow without a top-level `permissions:` block, or with `permissions: write-all`. Set the minimum (`contents: read` is a common default; bump per-job as needed). |
| **`pull_request_target` with PR checkout** | Workflow triggered by `pull_request_target` that then checks out the PR head — remote code execution to any PR opener. |
| **Secrets at workflow scope** | Secrets in `env:` at the workflow or job level rather than scoped to the single step that needs them. Third-party action steps inherit them. |
| **Secret echo / logging** | Commands that log their arguments (`curl -H "Authorization: $TOKEN"` with `set -x`, `echo` of any secret, debug flags in CI). |
| **Cache key without lockfile hash** | `cache-key: deps-${{ runner.os }}` — restored across dependency changes, can serve stale or poisoned packages. Include `hashFiles('**/package-lock.json')`. |
| **Container runs as root** | Dockerfile missing `USER nonroot` or equivalent. K8s pod without `securityContext.runAsNonRoot: true`. |
| **No `HEALTHCHECK` / no readiness probe** | Containers without health signals; orchestrator can't tell live from dead. |
| **Mutable `latest` tag in deployment** | `image: myorg/app:latest` in a manifest. Deploys are non-reproducible; rollback is undefined. |
| **Missing SBOM / signed provenance** | Production images built without an SBOM and without sigstore/cosign signing. No way to answer post-disclosure: "are we affected." |
| **Build-time secrets baked in** | `ARG` or `ENV` with a secret value in a Dockerfile — visible in `docker history`. Use `--secret` mounts or runtime injection. |
| **Untrusted code reaches signing keys** | Workflow that runs untrusted PR code and later in the same job context has access to release/signing credentials. Separate jobs with explicit privilege boundaries. |

Rice's design question: if a maintainer of any pinned action or base image went rogue tomorrow, what's the blast radius?

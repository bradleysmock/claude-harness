## Infrastructure as Code Panel

*Activation is governed by the trigger table in `context/panels/triggers.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Kief Morris** — *Infrastructure as Code*; pipeline-driven infra, immutable infrastructure, environment parity
- **Kelsey Hightower** — Kubernetes contributor, *Kubernetes the Hard Way*; pragmatic distributed systems, least configuration

**Morris's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Infrastructure is code; treat it as code** | IaC must be version-controlled, peer-reviewed, and applied by a pipeline — not from a developer's laptop. Drift between code and reality is a defect. |
| **Immutable infrastructure** | You don't patch a server; you replace it. Long-lived hand-modified resources accumulate undocumented configuration that vanishes when they die. |
| **Environment parity through composition** | Staging and production should differ only in scale and inputs, not in structure. A staging environment that uses different modules than production tests a different system. |
| **State is sacred** | Terraform state is the source of truth for "what exists." Local state files, unlocked remote state, committed `.tfstate` — every one is an outage waiting to happen. |
| **Tests for infrastructure exist** | `terraform plan` is not a test. Tools like Terratest, Checkov, tflint, kube-linter, conftest catch class-of-error mistakes before they reach apply. |

**Hightower's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Configuration over code** | The manifest is the API. Tools that generate manifests dynamically (templating-on-templating) obscure what actually gets applied. Prefer declarative YAML you can `cat` and understand. |
| **The smallest unit of deploy is the pod spec** | A Deployment without resource requests/limits is unschedulable predictably and unkillable under load. Without a `readinessProbe`, traffic routes to a pod that hasn't started. Without a `livenessProbe`, dead pods stay in rotation. |
| **Secrets are not config** | Kubernetes `Secret` resources are base64, not encrypted at rest by default. Real secrets live in a secret store (Vault, AWS Secrets Manager, GCP Secret Manager, External Secrets Operator) and are pulled at runtime. |
| **`:latest` is undefined** | An image tagged `:latest` resolves to whatever the registry has now. Rollback is undefined; reproducibility is impossible. Pin to digest. |
| **Default-deny network policy** | Without `NetworkPolicy`, every pod can reach every other pod. Start from deny-all and allow what's needed. |

*Synthesis:* Morris evaluates whether the IaC system is a *reliable mechanism* — does it converge, can you reason about state, does the pipeline match production. Hightower evaluates whether each runtime declaration is *operationally correct* — will it schedule, will it serve traffic safely, will it survive failure.

---

## Review Dimensions

---

### Dimension 20: Infrastructure as Code Discipline
*Morris, Hightower*

| Hazard | What to look for |
|--------|-----------------|
| **State stored locally or unlocked** | Terraform `backend "local"` in committed code; remote backend without state locking (DynamoDB, GCS object lock). Concurrent applies corrupt state. |
| **`.tfstate` / `terraform.tfvars` committed** | State files or secret-containing tfvars in git history. |
| **Hardcoded environment-specific values** | Account IDs, ARNs, IPs, region strings embedded in module bodies rather than passed as variables. |
| **`count` for resources that should be addressable** | `count = var.enabled ? 1 : 0` then `count = 3` later — every index shifts, every resource recreates. Use `for_each` with a stable map key. |
| **Missing `lifecycle` blocks** | Resources that must not be replaced (`prevent_destroy`), or whose mutable attributes are managed elsewhere (`ignore_changes`), without lifecycle protection. |
| **Wildcard IAM** | `Action: "*"` or `Resource: "*"` in IAM policies, K8s ClusterRoles with `verbs: ["*"]` / `resources: ["*"]`. |
| **K8s container as root** | Pod spec without `securityContext.runAsNonRoot: true` and `runAsUser:`. `allowPrivilegeEscalation: false` not set. `readOnlyRootFilesystem: true` absent without justification. |
| **Missing resource requests/limits** | Pod containers without `resources.requests` (unschedulable predictably) or `resources.limits` (OOM noisy neighbors). |
| **Missing or wrong probes** | `readinessProbe` absent → traffic to cold pods. `livenessProbe` checking the wrong endpoint → dead pods rotated in. `livenessProbe` that calls dependencies → cascading restarts. |
| **`:latest` image tag** | Any deployment manifest with a floating tag. Pin to digest or immutable tag. |
| **Secrets as K8s `Secret` only** | Sensitive material stored in `Secret` resources without an external secret manager (Vault, SOPS, External Secrets Operator). Base64 is not encryption. |
| **No `NetworkPolicy`** | Namespace without a default-deny `NetworkPolicy` — every pod reachable from every other. |
| **Implicit module ordering** | Modules that depend on each other through shared data sources or remote state without explicit dependency declaration. Apply ordering becomes a guessing game. |
| **Generated YAML without source review** | Helm templates or Kustomize overlays where the rendered output isn't pinned/inspected. The thing that runs is not the thing reviewed. |
| **Single-AZ / single-region production resource** | A production database, queue, or load balancer in one availability zone with no documented acceptance of the SPOF. |
| **No `PodDisruptionBudget`** | Multi-replica workload without a PDB. Node drains can take all replicas down simultaneously. |

Morris's design question: if you `terraform destroy` and then `terraform apply` from the current code, do you get the same infrastructure that's running now? If not, what's missing from code?

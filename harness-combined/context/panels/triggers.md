# Panel activation triggers

Canonical, machine-parseable source for which expert panels activate for a
given review scope. `panel_detect.py` reads this file and deterministically
maps `(project root, in-scope files)` to active panels — replacing the old
prose trigger table that used to live in the critique skill's SKILL file.

**Core** (`core.md`) is always active for any file in scope and has no entry
below. **Secondary** (`secondary.md`) is loaded on demand only when the
primary panels reach a genuine impasse — it is deliberately excluded from
this table (see the critique skill's Step 2 for its on-demand loading rule).

**Behavior change from the old prose table:** a `manifests` hit now activates
its panel *deterministically*, including on a docs-only review — e.g. a
review of only `README.md` in a Python repo (a `pyproject.toml` present at
root) now activates the Python panel, where the old model-judgment table
would sometimes reasonably skip it because no `.py` file was in scope. This
is a chosen tradeoff (0053/0057): a manifest is as much "this project speaks
Python" as any single file, and false-negative panel drops are worse than an
occasional over-broad activation.

Each entry is keyed by the panel's short name and names its panel file plus
zero or more typed trigger fields:

- `globs` — POSIX glob patterns matched against in-scope files' relative paths.
- `manifests` — filenames whose mere *presence* (root or in-scope) activates the panel.
- `deps` — dependency/package names looked up in manifests: parsed structurally
  for JSON/TOML (`package.json`, `pyproject.toml`, `Cargo.toml`), and via a
  word-boundary line regex for formats stdlib can't parse (`requirements.txt`,
  `go.mod`, `Gemfile`). Exact-name matching only — `preact` never matches `react`.
- `path_keywords` — case-insensitive substrings checked against each in-scope
  file's relative path.
- `content` — regexes matched against in-scope files' text (including string
  literals) — size-capped, never against manifest-only content.
- `judgment` — prose describing triggers that are irreducibly a model call;
  never encoded as a fake-deterministic pattern (0053). A panel with a
  `judgment` field but no matching deterministic trigger is emitted as a
  `candidate`, never silently dropped.

```toml
[panels.python]
file = "python.md"
globs = ["**/*.py"]
manifests = ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"]

[panels.typescript]
file = "typescript.md"
globs = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.mjs", "**/*.cjs"]
manifests = ["package.json", "tsconfig.json"]

[panels.angular]
file = "angular.md"
deps = ["@angular/core"]
manifests = ["angular.json"]
globs = [
    "**/*.component.ts", "**/*.component.html", "**/*.service.ts",
    "**/*.module.ts", "**/*.directive.ts", "**/*.pipe.ts",
]

[panels.react]
file = "react.md"
deps = ["react"]
globs = ["**/*.jsx", "next.config.*", "remix.config.*"]
content = ["from ['\"]react['\"]", "require\\(['\"]react['\"]\\)", '@vitejs/plugin-react']
# provenance: "component patterns" (JSX without an explicit react import, the
# new JSX transform) is not reliably regex-detectable — downgraded to judgment.
judgment = "A `.jsx`/`.tsx` file using JSX/component patterns with no explicit `react` import (new JSX transform) — confirm from context."

[panels.vue]
file = "vue.md"
deps = ["vue"]
globs = ["**/*.vue"]
manifests = ["nuxt.config.js", "nuxt.config.ts"]
content = ["@vitejs/plugin-vue"]

[panels.svelte]
file = "svelte.md"
deps = ["svelte", "@sveltejs/kit"]
globs = ["**/*.svelte"]
manifests = ["svelte.config.js", "svelte.config.ts"]
path_keywords = ["src/routes"]

[panels.solid]
file = "solid.md"
deps = ["solid-js", "@solidjs/start"]
globs = ["vite.config.*", "app.config.js", "app.config.ts"]
content = ["createSignal", "createEffect", "vite-plugin-solid"]

[panels.go]
file = "go.md"
globs = ["**/*.go"]
manifests = ["go.mod", "go.sum"]

[panels.rust]
file = "rust.md"
globs = ["**/*.rs"]
manifests = ["Cargo.toml", "Cargo.lock"]

[panels.jvm]
file = "jvm.md"
globs = ["**/*.java", "**/*.kt", "**/*.kts"]
manifests = ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"]

[panels.cpp]
file = "cpp.md"
globs = [
    "**/*.c", "**/*.h", "**/*.cpp", "**/*.cc", "**/*.cxx", "**/*.hpp", "**/*.hh", "*.cmake",
]
manifests = ["CMakeLists.txt"]

[panels.shell]
file = "shell.md"
globs = ["**/*.sh", "**/*.bash", "**/*.zsh", ".git/hooks/*", ".husky/*"]
content = ['^#!.*\b(sh|bash|zsh)\b']
# provenance: detecting a shell snippet embedded inside a Makefile/Dockerfile/
# CI YAML (rather than a standalone shell file) is not reliably regex-shaped.
judgment = "A shell snippet embedded inside a Makefile, Dockerfile, or CI YAML file rather than a standalone shell script."

[panels.http-api]
file = "http-api.md"
path_keywords = ["route", "handler", "controller", "endpoint", "view", "api", "resources"]
globs = ["app/routes/**"]
manifests = ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"]
# provenance: "`.go` with HTTP patterns" beyond the path-keyword list requires
# recognizing net/http handler signatures / router registrations — judgment.
judgment = "A `.go` file with HTTP-handler patterns (net/http signatures, router registrations) whose path does not already match a path keyword."

[panels.graphql]
file = "graphql.md"
globs = ["**/*.graphql", "**/*.gql"]
deps = [
    "graphql", "@apollo/client", "@apollo/server", "apollo-server",
    "graphql-yoga", "relay", "type-graphql", "strawberry-graphql", "ariadne", "gqlgen",
]
# provenance: a resolver map or schema-first/code-first server definition with
# no `.graphql`/`.gql` file and no matching dependency is a near-miss to this
# panel's own deterministic triggers, not reliably regex/glob-shaped.
judgment = "Resolver maps or schema-first/code-first server definitions with no `.graphql`/`.gql` file and no matching dependency."

[panels.grpc-protobuf]
file = "grpc-protobuf.md"
globs = ["**/*.proto", "**/*_pb2.py", "**/*.pb.go", "**/*_pb.ts", "**/*_grpc.rb"]
manifests = ["buf.yaml", "buf.gen.yaml"]
deps = ["grpc", "@grpc/grpc-js", "grpcio", "google.golang.org/grpc", "tonic", "grpc-java"]

[panels.dotnet]
file = "dotnet.md"
globs = [
    "**/*.cs", "**/*.csproj", "**/*.sln", "**/*.fs", "**/*.fsproj", "**/*.vb", "**/*.vbproj", "*.nuspec",
]
manifests = ["Directory.Build.props", "global.json", "packages.config"]

[panels.hypermedia]
file = "hypermedia.md"
deps = ["htmx"]
globs = ["**/htmx-ext-*"]
content = ['hx-[a-z-]+\s*=']

[panels.identity]
file = "identity.md"
deps = [
    "passport", "authlib", "next-auth", "jsonwebtoken", "jose", "pyjwt",
    "express-session", "iron-session", "flask-login", "bcrypt", "argon2",
    "scrypt", "passlib", "@simplewebauthn", "py_webauthn", "casbin", "cerbos",
]
path_keywords = ["/login", "/logout", "/oauth/", "/token", "/authorize", "/userinfo", "/.well-known/"]
content = ['\bopenid\b', 'django\.contrib\.auth', '@auth0/', '\blucia\b', '\bkeycloak\b', '\bhydra\b', 'JJWT', '\boso\b', '\bopa\b']
# provenance: identity-provider config recognized only by file convention
# (auth.js config, IdentityServer setup) rather than a dependency/import name.
judgment = "Config-file-based identity-provider setup (e.g. `auth.js`, IdentityServer) not named by a dependency or import."

[panels.cryptography]
file = "cryptography.md"
deps = [
    "cryptography", "pycryptodome", "pynacl", "noble-hashes", "noble-curves",
    "tweetnacl", "libsodium-wrappers", "ring", "rustls", "aes-gcm",
    "chacha20poly1305", "sodiumoxide",
]
content = [
    '\bimport hmac\b', '\bimport secrets\b', 'from hmac import', 'from secrets import',
    "require\\(['\"]crypto['\"]\\)", "from ['\"]crypto['\"]", '\bcrypto/[a-z]+\b',
    'golang\.org/x/crypto', 'filippo\.io/age', 'javax\.crypto', 'java\.security',
    'BouncyCastle', '\bTink\b', 'CryptoKit',
]

[panels.ui]
file = "ui.md"
globs = ["**/*.html", "**/*.css", "**/*.scss", "**/*.jsx", "**/*.tsx"]
path_keywords = ["static/", "public/", "templates/"]
# provenance: HTML markup embedded in a string literal inside a file whose
# extension doesn't already match (e.g. `render_template_string(...)` in a
# `.py` file) is not reliably regex-shaped without heavy false-positive risk.
judgment = "HTML markup inside a string literal in a file whose extension is not otherwise covered (e.g. `render_template_string` in a `.py` handler, inline JSX template literals)."

[panels.uswds]
file = "uswds.md"
deps = ["@uswds/uswds"]
content = ['usa-[a-z-]+', '_uswds-theme', 'uswds-init']
path_keywords = ["uswds"]

[panels.ai-llm]
file = "ai-llm.md"
deps = [
    "anthropic", "openai", "langchain", "litellm", "instructor", "ai",
    "langgraph", "llama_index",
]
content = ['\bpinecone\b', '\bqdrant\b', '\bweaviate\b', '\bchroma\b', '\bpgvector\b', 'bedrock', 'vertexai']
# provenance: an agent loop, tool-calling handler, or eval harness/dataset with
# no matching client dependency is a near-miss to this panel's own `deps`/
# `content` triggers, not reliably regex/glob-shaped.
judgment = "Agent loops, tool-calling handlers, or an LLM evaluation harness/eval dataset with no matching client dependency."

[panels.cicd]
file = "cicd.md"
globs = [
    ".github/workflows/**", ".gitlab-ci.yml", "Jenkinsfile", "Dockerfile*",
    "Makefile", ".pre-commit-config.yaml",
]
manifests = ["package-lock.json", "poetry.lock", "Cargo.lock", "go.sum", "yarn.lock", "pnpm-lock.yaml"]

[panels.database]
file = "database.md"
globs = ["**/migrations/**", "**/*.sql", "**/schema.rb", "**/schema.prisma"]
# provenance: an ORM model file or a file constructing raw queries with no
# migration directory, `.sql` file, or schema file in scope is a near-miss to
# this panel's own `globs`, not reliably regex/glob-shaped.
judgment = "ORM model files or files constructing raw queries with no migration directory, `.sql` file, or schema file in scope."

[panels.data-engineering]
file = "data-engineering.md"
globs = ["dags/**/*.py", "airflow.cfg", "dbt_project.yml", "models/**/*.sql", "**/schema.yml", "snapshots/**"]
deps = [
    "dagster", "prefect", "dbt-core", "pyspark", "apache-beam",
    "scikit-learn", "xgboost", "torch", "tensorflow", "mlflow", "feast", "tecton",
]
content = ['@dag\b', 'DAG\(', '@asset\b', '@op\b', '\bDefinitions\(', '@flow\b', '@task\b']

[panels.infrastructure]
file = "infrastructure.md"
globs = ["**/*.tf", "**/*.tfvars", "**/Chart.yaml"]
deps = ["aws-cdk-lib", "pulumi"]
content = ['^apiVersion:\s', '^kind:\s']
# provenance: an Ansible playbook or CloudFormation template is a near-miss to
# this panel's own deterministic triggers (no shared file extension or
# dependency name to key off), not reliably regex/glob-shaped.
judgment = "Ansible playbooks or CloudFormation templates with no `.tf`/`Chart.yaml` file and no CDK/Pulumi dependency."

[panels.testing]
file = "testing.md"
globs = ["**/tests/**", "**/__tests__/**", "**/*_test.*", "**/*.test.*", "**/*.spec.*", "conftest.py"]
manifests = ["pytest.ini", "jest.config.js", "vitest.config.ts"]

[panels.observability]
file = "observability.md"
deps = ["opentelemetry-api", "@opentelemetry/api", "prometheus-client", "prom-client", "winston", "pino"]
judgment = "Service entry points, request handlers, jobs, or queue consumers — role-based, not name/pattern-based."

[panels.performance]
file = "performance.md"
globs = ["**/*bench*/**", "**/*benchmark*"]
deps = ["pytest-benchmark", "criterion"]
# provenance: hot-path code not already named by a benchmark file or
# dependency is a near-miss to this panel's own `globs`/`deps`, not reliably
# regex/glob-shaped.
judgment = "Hot-path code (request handlers, loops over user-scaled collections, batch jobs, render loops) not already named by a benchmark file or dependency."

[panels.distributed]
file = "distributed.md"
deps = ["celery", "kombu", "pika", "boto3", "kafka-python", "confluent-kafka", "bullmq", "sidekiq"]
judgment = "Service-to-service code — queue producers/consumers, RPC/HTTP clients to owned services, webhook handlers, retry/idempotency/saga logic — role-based, not name/pattern-based."
```

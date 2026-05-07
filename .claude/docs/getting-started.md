# Getting Started

This guide walks you from zero to a generated, tested, and reviewed component in six stages.

---

## Prerequisites

Install the required tools for your target language before running the pipeline.

### Python

```bash
pip install pytest pytest-cov mypy ruff radon pip-audit pip-licenses pyyaml semgrep
```

### TypeScript / Node.js

```bash
npm install -g typescript eslint prettier
npm install --save-dev jest @types/jest ts-jest
```

### All Languages (recommended)

```bash
# Secrets detection
brew install gitleaks       # macOS
# or: pip install gitleaks  # Python wrapper

# SAST
pip install semgrep
```

---

## Step 1: Copy the `.claude` Folder

Copy the entire `.claude/` directory into the root of your project:

```bash
cp -r .claude/ /path/to/your/project/.claude/
cp CLAUDE.md /path/to/your/project/CLAUDE.md
```

---

## Step 2: Create the Pipeline Directory

```bash
mkdir -p /path/to/your/project/pipeline
```

---

## Step 3: Write Your Specification

Copy the template and fill it in:

```bash
cp .claude/templates/specification.yaml pipeline/spec.yaml
# Edit pipeline/spec.yaml
```

See `.claude/docs/specification-guide.md` for detailed guidance on writing high-quality specifications that pass Gate 1 consistently.

**The single most important step:** Write a clear, measurable specification. Every minute spent here saves ten minutes in remediation.

---

## Step 4: Start Claude Code

```bash
cd /path/to/your/project
claude
```

---

## Step 5: Run the Pipeline

**Option A — Full automation (recommended for well-specified tasks):**
```
/run-pipeline
```

**Option B — Stage by stage (recommended while learning the workflow):**
```
/intake    # Stage 1: validate spec
/design    # Stage 2: design artifact
/generate  # Stage 3: TDD code generation
/analyze   # Stage 4: quality gates
/review    # Stage 5: semantic review (requires human input)
/deliver   # Stage 6: integration and artifacts
```

**Check status at any time:**
```
/status
```

---

## What Gets Created

After a successful pipeline run, your project will contain:

```
project/
├── src/                         # Implementation code
├── tests/                       # Unit tests (TDD)
├── tests/integration/           # Integration tests
├── docs/
│   ├── api-reference.md         # API documentation
│   ├── complexity-report.md     # Complexity analysis
│   └── architecture/
│       └── module-graph.md      # Dependency graph
├── pipeline/
│   ├── spec.yaml                # Your specification (input)
│   ├── design-artifact.md       # Interface contracts
│   ├── adr.md                   # Architectural Decision Record
│   ├── analysis-report.md       # Stage 4 findings
│   ├── review-report.md         # Stage 5 review
│   └── security-review-record.md # Audit record
├── CHANGELOG.md                 # Updated with this component
└── README.md                    # Updated with component docs
```

---

## Resuming an Interrupted Pipeline

If Claude Code stops mid-pipeline, the state is preserved. Resume from where you left off:

```
/status          # Check which stages passed
/analyze         # Resume from the first incomplete stage
```

State is stored in `.claude/state/pipeline.json`.

---

## Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Gate 1 fails with score < 8 | Spec has unmeasurable NFRs or missing criteria | See `.claude/docs/specification-guide.md` |
| Stage 4 loops 2+ times | Generated code has systematic issues | Check `.claude/state/pipeline.log` for patterns |
| Secrets scan hard-blocks | Literal credentials in generated code | Remove and use env vars; check generation prompt for implicit examples |
| Coverage < 80% | Tests don't cover error paths | Add tests for every except/catch/if-error branch |
| Human review returns REJECT | Spec ambiguity surfaced as logic error | Improve spec and re-run from `/generate` |

---

## Pipeline Metrics

After several runs, use the pipeline log to identify patterns:

```bash
# Gate 1 rejection rate
grep "stage1.*FAIL" .claude/state/pipeline.log | wc -l

# Average remediation loops
grep "STAGE4.*Attempt" .claude/state/pipeline.log | wc -l

# Full pipeline log
cat .claude/state/pipeline.log
```

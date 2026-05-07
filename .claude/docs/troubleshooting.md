# Troubleshooting Guide

---

## Gate 1 Issues

### "Score X/10 is below the required threshold of 8"

**Diagnosis:** Run `/intake` and read the scoring breakdown.

**Most common causes and fixes:**

| Score gap | Likely cause | Fix |
|-----------|-------------|-----|
| Missing 2 NFR points | NFRs have no numbers | Add ms/MB/%/req values to every NFR |
| Missing 2 AC points | Criteria aren't Given/When/Then | Rewrite in testable form |
| Missing 1 context point | `codebase_context` is empty | Paste relevant interfaces |

---

### "Ambiguous terms detected"

Words like "fast", "secure", "appropriate" are detected as ambiguous.

**Fix:** Replace with measurements.
- "fast" → "p99 < 50ms"
- "secure" → name the specific security property (e.g., "validates all inputs against a schema", "uses bcrypt cost 12 for password hashing")
- "appropriate" → define the specific criterion

---

## Gate 4 (Analysis) Issues

### "Secrets scan: HARD BLOCK"

The secrets scanner found what appears to be a hardcoded credential.

**Steps:**
1. Read the finding — it will show the file and line number
2. If it's a real secret: remove it immediately; replace with `os.environ["VAR_NAME"]`
3. If it's a false positive (e.g., a test fixture with an obviously fake value): add a comment `# nosec` (Python) or `// nosemgrep` (JS) on the line, and document why it is a false positive in `.claude/state/pipeline.log`
4. If the secret may have been committed to git history: rotate the credential immediately before continuing

---

### "Type check: BLOCK — N type errors"

mypy or tsc found type errors in the generated code.

**Fix:** Do not use `# type: ignore` or `@ts-ignore` to suppress errors. Fix the underlying type issue:
1. If a function can return `None`, the return type must be `T | None`
2. If an external library lacks type stubs, install `types-<package>` or create a stub file
3. `Any` types require a justification comment

---

### "Coverage: BLOCK — Line coverage X% < 80%"

Generated tests don't cover enough of the implementation.

**Coverage report location:** `.claude/state/coverage.json` or the pytest terminal output

**Fix pattern:**
1. Look at the "missing" lines in the coverage report
2. Most uncovered lines are in error paths (`except` blocks, `if error:` branches)
3. Add tests that exercise each uncovered error path
4. Do not use `# pragma: no cover` to meet the threshold — this hides real gaps

---

### Stage 4 escalated after 2 remediation attempts

The automated loop couldn't fix the blocking findings.

**What to do:**
1. Run `/status` to see which specific checks are failing
2. Read `pipeline/analysis-report.md` for the full finding list
3. Fix the issues manually in the generated code
4. Re-run `/analyze` to restart the analysis pipeline

**Pattern:** If the same finding type recurs across runs, the root cause is usually in the specification (the requirement enables a vulnerable pattern) or the style guide (a constraint was not explicit enough).

---

## Stage 5 Human Review Issues

### Review rejected — "return to /generate with remediation notes"

The human reviewer rejected the implementation.

**Process:**
1. Read `pipeline/review-report.md` for the specific remediation notes
2. Understand whether the root cause is in the spec, the design, or the implementation:
   - **Spec issue:** the requirement was ambiguous and was interpreted incorrectly → fix the spec, re-run from `/intake`
   - **Design issue:** the interface contract was wrong → fix `pipeline/design-artifact.md`, re-run from `/generate`
   - **Implementation issue:** the code doesn't satisfy the design → re-run `/generate` with the remediation notes
3. Do not skip `/analyze` after re-generating

---

## Tool Availability Issues

### "semgrep not found"

```bash
pip install semgrep
```

### "mypy not found"

```bash
pip install mypy
```

### "radon not found"

```bash
pip install radon
```

### "pip-audit not found"

```bash
pip install pip-audit
```

### Tool installed but hook still fails

Check that the tool is on PATH for the shell that Claude Code runs hooks in:
```bash
which semgrep
which mypy
```

If not found, add the install path to `env.PATH` in `.claude/settings.json`.

---

## State File Issues

### "Pipeline state file not found"

The state file was deleted or never created.

**Fix:**
```bash
bash .claude/hooks/init-pipeline.sh
```

### Pipeline shows wrong stage as "next"

The state file may be out of sync with the actual work done.

**Fix:** Run each stage's command explicitly rather than `/run-pipeline`. Each command re-verifies its own pre-conditions.

### Want to restart the pipeline from scratch

```bash
rm .claude/state/pipeline.json
bash .claude/hooks/init-pipeline.sh
```

Then re-run from `/intake`.

---

## Performance

### Pipeline takes longer than 4 hours

Expected cycle time for well-specified tasks: < 4 hours.

Long cycle times are caused by:
1. **Multiple Stage 4 remediation loops** — root cause is usually an ambiguous spec allowing insecure patterns. Fix the spec.
2. **Large codebase context** — trim `codebase_context` to the most relevant interfaces only (< 4,000 tokens)
3. **Broad specification scope** — a single spec should describe a single component. Split large tasks into multiple pipeline runs.

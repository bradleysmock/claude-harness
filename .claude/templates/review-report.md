# Stage 5 — Semantic Review Report

**Component:** [Component name]
**Date:** [YYYY-MM-DD]
**Reviewer:** Automated (Claude Code) + Human
**Pipeline Run ID:** [from state file]

---

## Executive Summary

[3-sentence summary: overall code quality, primary concerns, and recommendation.]

---

## Finding Table

| ID | Severity | Dimension | File:Line | Description |
|----|----------|-----------|-----------|-------------|
| F-01 | CRITICAL/HIGH/MEDIUM/LOW | Correctness/Robustness/Security/Performance/Maintainability/Test Quality | src/x.py:42 | [brief description] |

**Finding counts by severity:**
- CRITICAL: [N]
- HIGH: [N]
- MEDIUM: [N] (includes carried forward from Stage 4)
- LOW: [N]

---

## Dimension Findings

### 1. Correctness

[Finding details or "No findings."]

**Unsatisfied acceptance criteria:** [NONE / list criteria that cannot be fully satisfied]

---

### 2. Robustness

[Finding details or "No findings."]

---

### 3. Security

[Finding details or "No findings."]

**Stage 4 MEDIUM findings adjudication:**

| Finding | Decision | Rationale |
|---------|----------|-----------|
| [SAST finding] | ACCEPT / ESCALATE | [reason] |

---

### 4. Performance

[Finding details or "No findings."]

**NFR compliance:** [All NFRs achievable / list NFRs at risk]

---

### 5. Maintainability

[Finding details or "No findings."]

---

### 6. Test Quality

[Finding details or "No findings."]

---

## Recommendation

**Automated recommendation:** [ ] APPROVE  [ ] APPROVE WITH CONDITIONS  [ ] REJECT

**Conditions (if applicable):**
- [Condition 1 — must be resolved before merge]

**Remediation notes (if rejected):**
- [Specific, actionable instruction 1]
- [Specific, actionable instruction 2]

---

## Human Review

**Reviewer:** ___________________
**Decision:** [ ] APPROVED  [ ] APPROVED WITH CONDITIONS  [ ] REJECTED
**Date:** ___________________
**Notes:** ___________________

[For CONFIDENTIAL/RESTRICTED:]
**Second Reviewer:** ___________________
**Decision:** [ ] APPROVED  [ ] REJECTED
**Date:** ___________________

---

*This report is part of the permanent pipeline audit record.*
*Retain alongside the security review record in `pipeline/security-review-record.md`.*

# Expert Code Critique

You are conducting a structured expert critique. Read every file in scope before writing a single finding. The output covers two scopes: **this change** (findings specific to the changed files) and **codebase patterns** (what this change reveals about systemic habits, good or bad, across the broader codebase).

---

## Step 1: Determine Active Panels

Based on the files in scope, determine which panels apply. Announce the active panels before reading any code or panel files.

| Files in scope | Panel | File |
|----------------|-------|------|
| Any file | **Core** | `${CLAUDE_PLUGIN_ROOT}/context/panels/core.md` |
| `app/**/*.py`, `tests/**/*.py` | **Python** | `${CLAUDE_PLUGIN_ROOT}/context/panels/python.md` |
| `app/routes/**` | **HTTP/API** | `${CLAUDE_PLUGIN_ROOT}/context/panels/http-api.md` |
| `app/templates/**`, `app/static/**` | **UI** | `${CLAUDE_PLUGIN_ROOT}/context/panels/ui.md` |
| `app/clients/**` or any LLM invocation | **AI/LLM** | `${CLAUDE_PLUGIN_ROOT}/context/panels/ai-llm.md` |

Panels are additive. A route file (`app/routes/sessions.py`) activates Core + Python + HTTP/API. A template file activates Core + UI. A service file activates Core + Python.

---

## Step 2: Load Panel Definitions

Read only the panel files for active panels. Core is always active. Do not read panel files for inactive panels.

The Secondary panel (`${CLAUDE_PLUGIN_ROOT}/context/panels/secondary.md`) is loaded on demand — only when the primary panels reach a genuine impasse that synthesis cannot resolve.

---

## Target

```
$ARGUMENTS
```

If `$ARGUMENTS` is empty, review all changed files (per `git diff --name-only`). If a specific file or glob is given, review those files. Read every file in scope before writing a single finding.

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
  Active panels: [Core | + Python | + UI | + HTTP/API | + AI/LLM]
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

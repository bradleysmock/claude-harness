---
name: critique
description: Apply domain-specialist panels to a chosen scope — Python idioms, HTTP/API design, UI patterns, AI/LLM security — each with a distinct mental model, not just a harder general scan. Scope is set by argument (files, globs, a git ref/range, or a scope keyword); when no argument is given the command ASKS which scope to run against, defaulting to the whole codebase focused on changes since the last critique — it does not silently assume uncommitted changes. Also produces a Codebase Patterns section that looks beyond the changed files to surface systemic habits. TRIGGER when the user wants a specific expert lens applied to a change, names a domain ("security review", "Python idioms", "what would an API designer say"), or asks for panel review (e.g. "critique the auth route", "panel review of the new handler", "what's wrong with this from an API design perspective"). SKIP for ticket-scoped post-build reviews (use the review skill, which reads problem/requirements/solution as baseline), for general correctness or style checks (use /code-review), and when the user only wants lint output (use /gate).
---

# Expert Code Critique

Conduct a structured expert critique. Read every file in scope before writing a single finding. The output covers two scopes: **this change** (findings specific to the changed files) and **codebase patterns** (what this change reveals about systemic habits across the broader codebase).

---

## Step 1: Determine Active Panels

`${CLAUDE_PLUGIN_ROOT}` is the root of the installed plugin and is injected at invocation time. If unset, resolve it as the directory containing this skill file.

Panel activation is deterministic, not a model judgment call. Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/panel_detect.py" --root <project_root> <files in scope...>
```

against the canonical trigger data in `${CLAUDE_PLUGIN_ROOT}/context/panels/triggers.md`, and parse its JSON output before reading any code or panel files:

- **`active`** — the panels to load, Core first. Announce these before reading any files.
- **`candidates`** — panels whose activation is irreducibly a model call (a `judgment` trigger) or, in `--design` mode, a file-content-dependent trigger that could not be evaluated. For **each** candidate, disposition it — activate or defer — with a one-line reason, before reading code. Never silently drop a candidate.
- **`skipped`** — files the script could not scan (oversize, unreadable, binary, missing, or outside `--root`). If non-empty, surface it in the report header (see Output Format below).

See "Design-artifact mode" below for how this script invocation and the findings differ when the scope is design artifacts rather than code.

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

**Considered-and-deferred panels.** `panel_detect.py`'s `candidates` list is the primary source for this, but a panel can also be *almost* activated by something the script can't see (e.g., an inline-content pattern that appears only in a comment, or a single match in a test fixture spotted while reading code). Record either kind as deferred rather than silently dropping it. The report header has a "Panels considered, deferred" line for this — see Output Format below.

**Design-artifact mode.** When the files in scope are design artifacts — `problem.md`, `requirements.md`, `solution.md`, README-style design docs, RFCs, ADRs (architectural decision records) — treat this as a *design review* rather than a code review. Typical invocation: `/critique problem.md requirements.md solution.md`. Infer the intended file scope from the artifacts' content — what languages, frameworks, integration points, identity layers, data systems, or LLM tooling the design proposes touching — then run `panel_detect.py --root <project_root> --design` (no file list) against that inferred scope. Root-evaluable triggers (manifest presence, root-manifest dependencies) still activate deterministically; file-content-dependent triggers surface as `candidates` for you to judge rather than being silently dropped. The same panel set fires; the lens is "is this design going to produce code that respects the panel's hazards?" rather than "does this code respect them?". Findings reference the artifact section (e.g., `solution.md § Auth flow`) rather than `file:line`. The Fix section names the design correction (e.g., "rework the auth section to specify Argon2id rather than 'a password hash'") rather than a code edit.

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

The critique has **two outputs with different destinations**:

1. **The full structured report → the file only.** Build the complete report (the template below) and write it to `<report-path>`. Do **not** print the full report to the terminal — not the Finding Table, not the BLOCKER/MAJOR Detail, not Codebase Patterns. The file is the complete artifact.
2. **A compact summary → the terminal.** After the file is written, print only the **Terminal summary** block defined below. This is the operator's entire on-screen output.

Do not read files or write anything until you have read all target files. The report is written to the harness critiques directory — **never** to `CRITIQUE.md` in the current working directory, and **never** inside a worktree.

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

**The block below is the written report — the contents of `<report-path>`, not terminal output.** It is structured for a reader who *skims first, dives second*. Verdict comes before findings so the reader knows whether to read on; the Finding Table is the punch list; BLOCKER/MAJOR Detail is the substantive read; MINOR/OBS findings stay in tabular form because the table row already says what's needed. Two-paragraph synthesis on a MINOR-severity stylistic note does not pull its weight.

```
═══════════════════════════════════════════════════════
  EXPERT CODE CRITIQUE
  Target: [file(s) reviewed]
  Active panels: [Core | + Python | + TypeScript/JS | + Angular | + React | + Vue | + Svelte | + SolidJS | + Go | + Rust | + JVM | + C/C++ | + Shell | + HTTP/API | + Hypermedia | + Identity | + Cryptography | + UI | + USWDS | + AI/LLM | + CI/CD | + Database | + Data Engineering | + Infrastructure | + Testing | + Observability | + Performance | + Distributed]
  Panels considered, deferred: [list of panels whose triggers were ambiguous, with one-line reason each — or "none"]
  Scope: [how scope was resolved — e.g. "since last critique (<base>..HEAD)", "uncommitted", "codebase", or the files/glob/ref given]
  Skipped files: [panel_detect.py's `skipped` list, path + reason each — omit this line entirely when `skipped` is empty]
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

### Terminal summary (the only thing printed to the operator)

After `<report-path>` is written, print **only** this compact block — nothing else. Never echo the full report, the Finding Table, per-finding detail, or Codebase Patterns to the terminal; those live in the file.

```
Critique complete — <verdict> · <N> BLOCKER · <N> MAJOR · <N> MINOR · <N> OBS
Scope: <resolved scope, e.g. since last critique (<base>..HEAD)>   Panels: <Core + …>
Must change to ship: <one sentence — the highest-leverage required fix, or "Approved as-is">
Top items:
  • [BLOCKER] C-01 — <one-line title>   (`file:line`)
  • [MAJOR]   C-04 — <one-line title>   (`file:line`)
Full report: <report-path>
```

Rules for the summary:
- List **only BLOCKER and MAJOR** one-liners under "Top items", capped at the five highest-impact. If there are none, replace the list with a single line: `No blockers or majors — see report for MINOR/OBS.`
- The counts, verdict, and "Must change to ship" line mirror the report's Verdict section exactly.
- Always end with the `Full report:` path so the operator can open the complete critique.
- When invoked with `--comment`, add one final line after the summary stating how many findings were posted to the PR (or why posting was skipped), per the `--comment` block above.

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

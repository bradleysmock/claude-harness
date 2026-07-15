---
description: Manual gate runner — runs the full gate suite against a ticket's worktree using the harnes
---
Manual gate runner — runs the full gate suite against a ticket's worktree using the harness MCP tools. Writes structured findings to `.tickets/XXXX-<slug>/gate-findings.md`.

## Ticket resolution

A ticket number argument is required. If none is provided, scan `.tickets/` (not `.tickets/completed/`) for tickets with `status: implementing` or `status: review-ready`. If exactly one exists, use it. Otherwise list candidates and stop. For direct ticket ID resolution, check `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/`.

Read each ticket's status via the **Ticket resolution** rule in `/Users/bradley/workspaces/claude-harness/harness-combined/context/harness-reference.md`: when a worktree `.worktrees/XXXX-<slug>` exists, its `.tickets/` copy of `status.md` is authoritative (it carries `implementing` / `review-ready`); the root copy shows only claim/terminal states.

## Steps

1. **Determine worktree path** from `status.md`: read the `branch` field (e.g. `ticket/XXXX-<slug>`), strip the `ticket/` prefix, resolve `.worktrees/XXXX-<slug>` relative to project root. Confirm the directory exists.

2. **Compute the changed-file set** (selective gate skipping, ticket 0030). In the worktree, run `git diff --name-only HEAD` to list the files changed against the last commit. On a non-zero exit (no `HEAD` yet, e.g. an initial commit), fall back to `git diff --name-only --cached`; if that also fails (git unavailable), use `changed_files=None`. `None` means "diff unknown — run every gate", preserving the pre-0030 behaviour exactly. An empty result (a diff that lists no files) is also treated as run-all. Only pass a **non-empty** list to enable skipping.

3. **Run structured gates** via the MCP tool, passing the computed `changed_files`:
   ```
   gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root, fail_fast=False, changed_files=<list-or-None>)
   ```
   This runs all gates (no fail-fast) for **every** detected language stack and returns the complete picture including passed gates. When `changed_files` is a non-empty list, a gate whose file-scope patterns do not overlap it is **skipped** (a passing result with `skipped: true` and `skip_reason: "no relevant changes"`) rather than run; the outer response then carries `"any_skipped": true`. On a polyglot repo (e.g. Python backend + TypeScript frontend) the response carries a `languages` list and a pre-rendered `findings_md` body.

4. **Annotate known-flaky failures (in-memory, before writing)**: when the gate run produced any failures, load `.harness/flaky-report.json` and call `flaky_detect.annotate_failures(failures, report_path)`. Matching failures (a failure whose test matches a flaky test in the report) are labelled `known flaky (X/N)` **in-memory**, before `gate-findings.md` is written, so the whole file is a single atomic write (no TOCTOU window between reading the report and writing findings).

   **Fail closed**: if `.harness/flaky-report.json` is absent, unreadable, or unparseable, `annotate_failures` returns every failure unchanged — all failures remain hard blockers — and the error is logged. A missing or malformed flaky report never downgrades a failure. (When the run used the pre-rendered `findings_md` body, apply the annotation to that body's failure lines before writing it verbatim.)

5. **Write `.tickets/XXXX-<slug>/gate-findings.md`** (a single write, using the in-memory annotated failures from step 4). When the response includes `findings_md`, write it verbatim under the header. Otherwise render the same structure yourself:

   ```markdown
   # Gate Findings — XXXX-<slug>

   **Run at**: YYYY-MM-DD HH:MM
   **Worktree**: .worktrees/XXXX-<slug>
   **Languages detected**: <language(s), comma-separated>

   ## <language> / <gate-name>

   **Status**: PASS | FAIL | SKIP
   **Duration**: NNNms

   <For each failing error:>
   - `<file>:<line>` [`<code>`]: <message>

   <"clean" if no errors>
   ```

   A gate the run skipped (`skipped: true` in its result) renders with `**Status**: SKIP` and a `**Reason**: <skip_reason>` line (e.g. `no relevant changes`) in place of the error list — it is not a failure and never makes the run non-zero. One section per gate, per language, in the order they ran. Section headings are `## <language> / <gate-name>` when more than one language is detected; with a single language the heading is the bare `## <gate-name>` and the header reads `**Language detected**: <language>` (singular) — this preserves the pre-polyglot single-language report shape. A failure annotated in step 4 carries its `known flaky (X/N)` label inline in the message.

   **Skipped Tools section (ticket 0043).** A `TOOL_SKIPPED` entry is different from a `skipped: true` gate: it rides on a gate that **passed** because an *optional* tool was not installed (e.g. `staticcheck` for Go, `cargo-audit` for Rust) — distinct from `TOOL_ERROR` (the tool was present but crashed, which fails the gate). Whenever any gate result carries a `TOOL_SKIPPED` entry, the renderer appends a trailing `## Skipped Tools` section listing each absent tool with its gate and one-line message; those warnings are **not** repeated as per-gate findings, so the tool's own gate section still reads `clean`. The section is informational and never makes the run non-zero — provision the missing tools via the ticket 0022 doctor.

6. **Print summary line**: one `<language>=<PASS|FAIL: gate-names-failing>` token per detected language, e.g. `gate: python=PASS typescript=FAIL: lint`. With a single language this collapses to the original `gate: <language>=<PASS|FAIL: gate-names-failing>`. A gate that fails in **any** language makes the overall run non-zero.

   If the response is a `CONFIG_ERROR` (a malformed `[gates]` override block in `_standards.md`), report it as a failing run and surface the `CONFIG_ERROR` finding — the gate fails closed and does **not** fall back to the default commands.

## SARIF output (`--sarif`)

SARIF (Static Analysis Results Interchange Format) 2.1.0 is the machine-readable format read by the VS Code Problems panel, GitHub Code Scanning, and multi-tool CI dashboards. SARIF emission is **opt-in** and additive — it never alters `gate-findings.md`.

6. **Emit SARIF (opt-in only)**: after `gate-findings.md` is written, emit a SARIF file when *either* trigger is set:
   - The `--sarif` flag was passed to this command, **or**
   - `.tickets/_standards.md` (in the harness project root) contains a line matching the regex `^\s*sarif_output\s*:\s*true\s*$`. The value is matched **case-sensitively**: only the exact lowercase `sarif_output: true` enables emission. Python-capitalized `True` / `yes` / `on` / `1` are **intentionally not matched** (no accidental enable from a differently-spelled truthy token). This opt-in is enforced in code by `sarif_output.sarif_optin_enabled(project_root)`, which reads only the harness-root file.

   **Scope of authority**: only `.tickets/_standards.md` in the *harness project root* enables emission. A `_standards.md` inside the scanned worktree has **no authority** to turn SARIF output on — the project under analysis cannot enable emission of its own findings.

   When triggered, pass `emit_sarif=True` to the MCP tool:
   ```
   gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root, fail_fast=False, emit_sarif=True)
   ```
   This writes `.harness/results.sarif` (anchored on the gated directory) with one SARIF `run` per gate tool that produced findings. File locations are POSIX-relative paths contained within the worktree — absolute CI-runner paths never leak into the uploaded SARIF.

   **Non-fatal write**: if the SARIF file cannot be written (e.g. a read-only filesystem), the run is unaffected — the JSON response carries `sarif_write_failed: true` and the gate verdict is otherwise unchanged. A SARIF write failure never fails a gate run.

## Inline PR comments (`--comment`)

Posting findings as inline GitHub PR review comments is **opt-in** via `--comment`; the default is terminal output only. When the flag is set, after `gate-findings.md` is written, parse it and post:

```python
from pathlib import Path
from gates.finding_parser import parse_gate_findings
from gates.pr_commenter import post_findings, format_summary

worktree = Path(".worktrees/XXXX-<slug>")
findings = parse_gate_findings(worktree / ".tickets/XXXX-<slug>/gate-findings.md", worktree)
result = post_findings(findings, worktree, should_post=True, kind="gate", cwd=worktree)
print(format_summary(result))   # "Posted N inline comments (M skipped as duplicates)."
```

`post_findings` detects the open PR for the branch, routes each finding inline (when its `file:line` is in the PR diff) or to a single top-level comment (off-diff or no location), deduplicates against existing comments, and submits the inline batch in one `gh api .../reviews` call. It **falls back to terminal output** (with a specific reason) when `gh` is missing/unauthenticated, when no open PR exists, or when the existing-comment fetch fails — never blocking the run and never posting duplicates. Without `--comment`, do not call `post_findings` (or call it with `should_post=False`, which posts nothing and makes no `gh` calls).

## Notes

- This command **does not fix findings** — it records them. The caller decides what to do.
- The structured `file:line` error locations in `gate-findings.md` are what the critic reads to avoid re-flagging gate issues.
- `/build` calls this automatically; run it manually when you need a fresh gate report without re-running the full build cycle.

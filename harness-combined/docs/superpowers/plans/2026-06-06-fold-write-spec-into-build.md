# Fold `/write-spec` into `/build` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/build` generate specs inline from `solution.md` (ticket) or a description (standalone) when they're missing, so the common path is one command instead of `/write-spec` then `/build` — losing no quality gate.

**Architecture:** Pure prompt/markdown change to the harness flow files. `/build`'s "stop, run /write-spec first" branch is replaced by an inline call into the existing `write-spec-*.md` procedures (which already hold the score-spec gate, status check, and spec templates — reused, not duplicated). Spec/task files still land on disk, so DAG/checkpoint/resume are untouched. `/write-spec` and `/deliver` stay as-is.

**Tech Stack:** Markdown instruction files only. No engine code, no unit tests. Verification is grep + a two-ticket dry-run.

**Source spec:** `docs/superpowers/specs/2026-06-06-fold-write-spec-into-build-design.md`

---

## File map

| File | Change |
|---|---|
| `context/flows/build-ticket.md` | Step 1 rewrite: auto-spec branch + relocated score-spec/status gate |
| `context/flows/build-spec.md` | Step 0 rewrite: id-vs-description disambiguation + inline spec-mode generation |
| `commands/build.md` | Mode descriptions no longer assume pre-existing specs |
| `CLAUDE.md` | Pipeline diagrams mark `/write-spec` optional; `/clear` note → just `/build` |
| `context/harness-reference.md` | Note that `/build` self-specs when entering from `solution` |
| `README.md` | Pipeline + command catalog reflect self-speccing |

> **Note on edit targets:** Per CLAUDE.md, edit the **project-root** copies (the paths above), not the plugin-cache copies under `~/.claude/plugins/`.

---

### Task 1: Rewrite `build-ticket.md` Step 1 (the core change)

**Files:**
- Modify: `context/flows/build-ticket.md:7-22`

- [ ] **Step 1: Replace the Step 1 section**

Replace this exact block (lines 7–22):

````markdown
## Step 1 — Resolve ticket and find specs

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md` to get the slug.

If `status` is `changes-requested`, the worktree already exists from a prior `/build`. Skip Step 2; resume with the existing worktree and skip already-passed specs via `checkpoint(action="read", ...)`.

Find the spec or task for this ticket:
- `.harness/tasks/XXXX-<slug>.py` — multi-spec task (preferred if it exists)
- `.harness/specs/XXXX-<slug>*.py` — individual spec(s)

If neither exists, tell the user to run `/write-spec XXXX` first and stop.

If `.tickets/_standards.md` exists, load it via `@.tickets/_standards.md`.
If `.tickets/_learnings.md` exists, load it via `@.tickets/_learnings.md`.

Both are lead-curated. The model treats them as hard constraints, not suggestions. The machine's BM25 failure trail (`.harness/memory.db`) is consulted only by `memory(action="retrieve", ...)` during repair — it never feeds back into these files automatically.
````

with:

````markdown
## Step 1 — Resolve ticket, ensure specs exist

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md` to get the slug.

If `status` is `changes-requested`, the worktree already exists from a prior `/build`. Skip Step 2; resume with the existing worktree and skip already-passed specs via `checkpoint(action="read", ...)`.

Find the spec or task for this ticket:
- `.harness/tasks/XXXX-<slug>.py` — multi-spec task (preferred if it exists)
- `.harness/specs/XXXX-<slug>*.py` — individual spec(s)

**If specs exist** — continue to the standards/learnings load below.

**If neither exists** — generate them inline before building (this replaces the old "run `/write-spec` first" hand-off):

1. Perform **Steps 1–5** of `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-ticket.md` (resolve + score-spec gate → read only the named files → choose single-spec vs DAG → write the spec/task files). **Skip that flow's Step 6 report** — you are continuing into the build, not handing off.
2. **score-spec is a hard stop.** That flow's Step 1 runs the score-spec gate; if its verdict is **BLOCK**, stop here — **before any worktree is created** — show the failing checks, and tell the lead to fix the design artifacts (or run `/refine XXXX`) and re-run `/build XXXX`.
3. **Status precondition** is enforced by that flow's Step 1: if `status` is not `solution`, it stops and directs the lead to run `/problem XXXX` first. Honor that stop.
4. After the files are written, announce in one line: "No specs found — generated N spec(s)/task from `solution.md` (score-spec: PASS|WARN). Continuing to build."

Then load lead-curated context (both the specs-exist and just-generated paths):

If `.tickets/_standards.md` exists, load it via `@.tickets/_standards.md`.
If `.tickets/_learnings.md` exists, load it via `@.tickets/_learnings.md`.

Both are lead-curated. The model treats them as hard constraints, not suggestions. The machine's BM25 failure trail (`.harness/memory.db`) is consulted only by `memory(action="retrieve", ...)` during repair — it never feeds back into these files automatically.
````

- [ ] **Step 2: Verify the edit**

Run: `grep -n "generate them inline\|score-spec is a hard stop\|run /write-spec XXXX first" context/flows/build-ticket.md`
Expected: the first two phrases present; the old "run /write-spec XXXX first and stop" phrase **absent**.

- [ ] **Step 3: Commit**

```bash
git add context/flows/build-ticket.md
git commit -m "feat: /build ticket mode auto-generates specs from solution.md when absent"
```

---

### Task 2: Rewrite `build-spec.md` Step 0 (standalone disambiguation)

**Files:**
- Modify: `context/flows/build-spec.md:7-12`

- [ ] **Step 1: Replace the Step 0 section**

Replace this exact block (lines 7–12):

````markdown
## Step 0 — Detect spec or task

- `.harness/specs/$ARGUMENTS.py` → **spec path**
- `.harness/tasks/$ARGUMENTS.py` → **task path**

If neither exists, tell the user to run `/write-spec <description>` first.
````

with:

````markdown
## Step 0 — Detect spec, task, or free-form description

Decide by what `$ARGUMENTS` is and whether a file matches:

- **Existing spec file** — `.harness/specs/$ARGUMENTS.py` exists → **spec path** (below).
- **Existing task file** — `.harness/tasks/$ARGUMENTS.py` exists → **task path** (below).
- **Bare id, no match** — `$ARGUMENTS` is a single token (no whitespace) and no file matches → **stop**. Tell the user no spec/task named `$ARGUMENTS` exists, and they can pass a description or check the id. Do **not** treat a bare token as a description — this guards against a typo'd id silently triggering a full codebase exploration.
- **Free-form description** — `$ARGUMENTS` contains whitespace (e.g. `add bulk-export endpoint`) → generate the spec inline first: perform the full `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-spec.md` procedure (explore the codebase, write the spec or task DAG to `.harness/specs/` / `.harness/tasks/`). Announce the generated id(s), then continue on the spec or task path below using that id.
````

- [ ] **Step 2: Verify the edit**

Run: `grep -n "Bare id, no match\|Free-form description\|write-spec-spec.md" context/flows/build-spec.md`
Expected: all three present; old "run `/write-spec <description>` first." line absent.

- [ ] **Step 3: Commit**

```bash
git add context/flows/build-spec.md
git commit -m "feat: /build spec mode generates a spec from a description when none exists"
```

---

### Task 3: Update `commands/build.md` mode descriptions

**Files:**
- Modify: `commands/build.md:9` and `commands/build.md:12`

- [ ] **Step 1: Update the ticket-mode description**

Replace:

```markdown
- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` with a `solution.md` and one or more specs at `.harness/specs/<arg>*.py`.
```

with:

```markdown
- **Ticket mode** — argument begins with four digits (e.g. `0001`, `0023-add-inventory`). A ticket directory exists at `.tickets/<arg>*/` with an approved `solution.md`. Specs need not exist yet — `/build` generates them from `solution.md` if absent (the optional `/write-spec XXXX` can pre-generate or hand-tune them first).
```

- [ ] **Step 2: Update the spec-mode description**

Replace:

```markdown
- **Spec mode** — anything else (a bare spec-id or task-id under `.harness/specs/<id>.py` or `.harness/tasks/<id>.py`). No ticket, no worktree.
```

with:

```markdown
- **Spec mode** — anything else: a bare spec-id/task-id under `.harness/specs/<id>.py` / `.harness/tasks/<id>.py`, or a free-form description. A description with no matching spec file makes `/build` generate the spec first. No ticket, no worktree.
```

- [ ] **Step 3: Verify and commit**

Run: `grep -n "generates them from\|generate the spec first" commands/build.md`
Expected: both present.

```bash
git add commands/build.md
git commit -m "docs: build command modes no longer require pre-existing specs"
```

---

### Task 4: Update `CLAUDE.md` pipeline diagrams and session-boundary note

**Files:**
- Modify: `CLAUDE.md` (pipeline block ~line 17-19, standalone block ~line 25-26, session boundary line 40)

- [ ] **Step 1: Update the main pipeline block**

Replace:

```
/write-spec XXXX   specs derived from solution.md (no re-exploration)
/build XXXX        worktree → spec engine → write target files → diff
```

with:

```
/write-spec XXXX   (optional) pre-generate or hand-tune specs from solution.md
/build XXXX        auto-generates specs from solution.md if absent → worktree → spec engine → diff
```

- [ ] **Step 2: Update the standalone block**

Replace:

```
/write-spec <description>   explore codebase → spec
/build <spec-id>            gate engine (temp dir) → artifact
```

with:

```
/write-spec <description>      (optional) pre-generate a spec from a description
/build <description|spec-id>   generates a spec from a description if needed → gate engine (temp dir) → artifact
```

- [ ] **Step 3: Update the session-boundary note**

Replace:

```markdown
- **Session boundary**: After Checkpoint 1, the lead should `/clear` before running `/write-spec XXXX` and `/build XXXX`. This keeps each phase's context lean.
```

with:

```markdown
- **Session boundary**: After Checkpoint 1, the lead should `/clear` before running `/build XXXX` (which now self-generates specs from `solution.md`). This keeps each phase's context lean.
```

- [ ] **Step 4: Verify and commit**

Run: `grep -n "auto-generates specs\|(optional) pre-generate\|self-generates specs" CLAUDE.md`
Expected: three matches.

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md pipeline marks /write-spec optional, /build self-specs"
```

---

### Task 5: Add self-spec note to `harness-reference.md`

**Files:**
- Modify: `context/harness-reference.md` (after the status-transitions table, ~line 47)

- [ ] **Step 1: Add a note under the status-transitions table**

Find the blank line immediately after this table row:

```markdown
| `cancelled`         | `/cancel`                       | — (terminal)                          |
```

Insert this note directly below the table (before the next `---`):

```markdown
> **Self-speccing:** `/write-spec` never changed `status`; the `solution → implementing` transition has always been driven by `/build` setup. As of the merged build flow, `/build` also *generates* the spec/task files inline when it starts from `status: solution` with no specs present. `/write-spec` is therefore an optional pre-step, not a required transition.
```

- [ ] **Step 2: Verify and commit**

Run: `grep -n "Self-speccing" context/harness-reference.md`
Expected: one match.

```bash
git add context/harness-reference.md
git commit -m "docs: note that /build self-generates specs from the solution status"
```

---

### Task 6: Update `README.md` pipeline and command catalog

**Files:**
- Modify: `README.md:20-21`, `README.md:30-31`, `README.md:134-135`

- [ ] **Step 1: Update the ticket pipeline lines (20–21)**

Replace:

```
/write-spec XXXX   → reads solution.md → .harness/specs/ (no re-exploration needed)
/build XXXX        → worktree → spec engine → write target files → diff shown → post-build critic
```

with:

```
/write-spec XXXX   → (optional) pre-generate specs from solution.md into .harness/specs/
/build XXXX        → auto-generates specs from solution.md if absent → worktree → spec engine → diff → post-build critic
```

- [ ] **Step 2: Update the standalone pipeline lines (30–31)**

Replace:

```
/write-spec <description>   → explore codebase → .harness/specs/<id>.py
/build <spec-id>            → gate engine (temp dir) → artifact
```

with:

```
/write-spec <description>      → (optional) pre-generate a spec into .harness/specs/<id>.py
/build <description|spec-id>   → generates a spec from a description if needed → gate engine (temp dir) → artifact
```

- [ ] **Step 3: Update the command catalog rows (134–135)**

Replace:

```markdown
| `/write-spec <arg>` | Single entry point for spec authoring. Routes to ticket flow (digit-prefixed arg) or spec flow (free-form description). |
| `/build <arg>` | Single entry point for implementation. Routes to ticket flow (worktree + diff) or spec flow (temp dir + artifact). |
```

with:

```markdown
| `/write-spec <arg>` | **Optional** spec-authoring step. Routes to ticket flow (digit-prefixed arg) or spec flow (free-form description). `/build` self-specs when specs are absent, so this is only needed to pre-generate or hand-tune a spec. |
| `/build <arg>` | Single entry point for implementation. Generates specs first if none exist for the ticket/description, then routes to ticket flow (worktree + diff) or spec flow (temp dir + artifact). |
```

- [ ] **Step 4: Verify and commit**

Run: `grep -n "self-specs\|generates a spec from a description\|Generates specs first" README.md`
Expected: at least three matches.

```bash
git add README.md
git commit -m "docs: README reflects /build self-speccing; /write-spec marked optional"
```

---

### Task 7: Dry-run verification

No automated tests exist for prompt flows — validate by reading the merged flow end-to-end and confirming the two scenarios from the spec.

- [ ] **Step 1: Confirm the specs-exist path is unchanged**

Read `context/flows/build-ticket.md` Step 1. Confirm: when spec/task files already exist, control falls straight through to the standards/learnings load and into Step 2 (worktree) with no new behavior. This protects re-builds and `changes-requested` resume.

- [ ] **Step 2: Trace the auto-spec path**

Read `context/flows/build-ticket.md` Step 1 + `context/flows/write-spec-ticket.md` Steps 1–5. Confirm the chain: status≠solution → stop (`/problem`); score-spec BLOCK → stop **before** worktree; otherwise spec files written → announce → Step 2 worktree. Confirm no worktree/branch/status-mutation step can run ahead of the score-spec BLOCK check.

- [ ] **Step 3: Trace the standalone disambiguation**

Read `context/flows/build-spec.md` Step 0. Confirm: bare unknown id → stop; multi-word description → `write-spec-spec.md` then build; existing id → unchanged.

- [ ] **Step 4: Cross-reference check**

Run: `grep -rn "run /write-spec XXXX first\|run \`/write-spec" context/ commands/ CLAUDE.md README.md`
Expected: no remaining instruction that *forces* `/write-spec` as a prerequisite (only optional mentions remain).

- [ ] **Step 5: Final commit (if any cleanup was needed)**

```bash
git add -A
git commit -m "docs: finalize /write-spec-into-/build merge" || echo "nothing to finalize"
```

---

## Self-review

- **Spec coverage:** Ticket auto-spec (Task 1), standalone disambiguation (Task 2), command-mode docs (Task 3), CLAUDE.md (Task 4), harness-reference (Task 5), README (Task 6), verification dry-run (Task 7). Every file in the spec's "Files to change" list has a task. ✓
- **Preserved gates:** score-spec BLOCK relocated, not dropped (Task 1 Step 1, item 2); spec files still written (reuse of write-spec Steps 4–5); `/write-spec` and `/deliver` untouched. ✓
- **No placeholders:** every edit shows exact old/new text and a grep verification. ✓
- **Consistency:** the auto-spec branch reuses `write-spec-ticket.md` Steps 1–5 rather than copying templates, so spec-file format stays single-sourced. ✓

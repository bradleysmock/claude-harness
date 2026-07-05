# Harness Review — 2026-07-05

Review of the `/problem` → `/autopilot` pipeline and the `/critique` expert-panel workflow,
with the goal of improving the quality, security, and performance of generated output
**without adding human review points**. Every recommendation below is automation-shaped:
a deterministic gate, a persisted artifact, or a prompt/flow fix — not a new checkpoint.

Method: full read of `commands/`, `context/flows/`, `context/panels/` (core + samples),
`context/rules/`, `skills/`, `agents/critic.md`, `server.py`, `gates/*.py`, `hooks/*.py`,
`memory.py`, and the plugin manifest.

Severity: **HIGH** = can silently degrade shipped output or break a flow · **MED** = quality
leak with a cheap fix · **LOW** = polish / consistency.

---

## Summary — the five highest-leverage fixes

1. **Finish the branch-at-claim migration (A1).** Four flows still commit post-claim state to
   `main`, and every resolver reads the stale `main` copy of `status.md`. This is the largest
   internal inconsistency in the harness.
2. **Close the gate-gaming loopholes (A2, B1).** The repair loop can pass gates by weakening
   tests or adding the very suppression pragmas (`# nosec`, `# noqa`, `eslint-disable`) that
   `pre_write_guard` explicitly honors. Nothing detects this.
3. **Stop scoping the Jest gate to changed test files (B2).** As written, an implementation
   change that breaks an existing test passes the TypeScript gate.
4. **Persist critic findings and escalation diagnoses (A4, A5).** The two most valuable
   review artifacts the pipeline produces are currently discarded after display.
5. **Make missing tools loud (B4).** staticcheck, cargo-audit, and every stop-hook gate
   silently pass when the tool isn't installed — the enforcement layer can quietly be zero.

---

## A. Pipeline findings (/problem → /autopilot)

### A1 · HIGH — Incomplete branch-at-claim migration: stale `main` status + commits that violate the two-commits invariant

`context/harness-reference.md` (§ Status transitions, § Squash delivery) is unambiguous:
after the claim stub, **every** state (`solution`, `implementing`, `review-ready`,
`changes-requested`) and every design artifact is **branch-only**; `main` carries exactly the
`claimed` commit and the delivery squash. But:

- `context/flows/autopilot-ticket.md` Step A commits `status: changes-requested` **to main**
  (`git add .tickets/XXXX-slug/` at repo root), while the equivalent interactive path
  (`build-ticket.md` Step 7d) correctly commits it inside the worktree. The two paths leave
  the repo in different states for the same event.
- `skills/review/SKILL.md` Step 7 commits `changes-requested` to `main`.
- `commands/refine.md` Step 5 and the autopilot mode rule 6 commit revised `solution.md`
  to `main` — but post-claim, `solution.md` exists only in the worktree; `main`'s
  `.tickets/XXXX/` holds just the claim stub.
- `context/spec-remediation.md` asserts "No worktree yet … a worktree is created only once
  the verdict is PASS/WARN" and commits remediated artifacts to `main` — both statements
  predate branch-at-claim (the worktree now exists from `/problem` Phase 1). `build-ticket.md`
  Step 1.2 has the same remnant ("stop here — before any worktree is created").
- **Resolver staleness:** `commands/autopilot.md`, `build-ticket.md` Step 1,
  `write-spec-ticket.md` Step 1, `commands/gate.md`, and `deliver-ticket.md` Step 1 all
  resolve the ticket by reading root `.tickets/XXXX/status.md` — which, per the invariant,
  says `claimed` until delivery. Taken literally, `/autopilot XXXX` would refuse every
  correctly-claimed ticket ("not at status: solution"), and `/deliver` could never confirm
  `review-ready`. In practice the model fudges this; the docs should not rely on that.

**Fix:** (1) Add a single *resolution rule* to `harness-reference.md`: if
`.worktrees/<slug>/.tickets/<slug>/status.md` exists it is authoritative; the root copy is
only the claim signal. Update the five resolver flows to cite it. (2) Change autopilot Step A,
review Step 7, refine Step 5/rule 6, and spec-remediation S1/S2 to commit in the worktree on
the branch, matching `build-ticket.md` Step 7d. (3) Delete the "before any worktree is
created" remnants from `spec-remediation.md` and `build-ticket.md`.

### A2 · HIGH — The repair loop can game the gates; nothing detects test-weakening

`build-ticket.md` Steps 4e/7a and `repair-escalation.md` say "fix the specific `file:line`
locations", but nothing forbids or detects the classic degenerate repairs: deleting or
skipping a failing test, loosening an assertion, adding `# noqa` / `# type: ignore` /
`@ts-expect-error` / `as any` / `# nosec`, or downgrading types until mypy/tsc pass.
Worse, `hooks/pre_write_guard.py:47-54` treats `nosec`, `nolint`, `eslint-disable`,
`@ts-expect-error`, `# noqa` as *justification markers that bypass the guard* — the exact
tokens a gaming repair would add. The critic re-review is the only backstop, and
`critic-brief.md` never asks it to compare tests across repair rounds.

**Fix (all deterministic, no human):**
1. Add a **repair-integrity check** to the repair loop: after each repair round, diff the
   worktree against the pre-repair commit and fail the round if it (a) deletes or skips tests
   (`-` lines matching `def test_` / `it(` / `#[test]` / `func Test`, or added `skip`/`xfail`
   markers), or (b) adds suppression pragmas. Implement as a small pure function in `gates/`
   (like `spec_remediate.py`) and call it from Step 4e/7a; violations re-enter repair with an
   explicit "restore the test; fix the implementation" instruction.
2. In `pre_write_guard`, require justification markers to carry a reason
   (`# nosec: <why>`), and have the Stop hook count net-new suppressions on the branch diff
   and report them as findings.
3. Add one line to `critic-brief.md` Step 2.5 (code mode): "Compare the worktree's tests
   against `solution.md`'s Test Plan **and** against prior repair-round commits; weakened or
   deleted tests are BLOCKER."

### A3 · HIGH — Critic round-cap contradiction

`agents/critic.md:13` says "Round: 1 or 2 (rounds are capped at 2)". But
`build-ticket.md` Step 7a re-spawns the critic up to `MAX_REPAIR_ATTEMPTS + 1` rounds, and
`repair-escalation.md` adds up to two more batches (Phases 1–2). A literal critic could refuse
Round 3+, or behave as if the cap licenses it to stop reviewing. The 2-round cap is a
*design-phase* rule (`problem.md` Phase 5).

**Fix:** Remove the cap from `agents/critic.md` (round budgets are owned by callers) or
restate as "design phase: max 2; code phase: round number supplied by the caller."

### A4 · MED — Critic findings evaporate

Post-build critic reports are only "displayed verbatim". They are not written anywhere.
Consequences: `/deliver` Step 5's candidate-learnings scan reads only `gate-findings.md` and
commit messages, so recurring *critic*-level patterns (the interesting ones — design flaws,
missing tests) never become `_learnings.md` candidates; after escalation + `/clear`, the lead
resumes `/build` with no durable record of what the critic found or what each repair round
attempted; `/review` re-derives everything from scratch.

**Fix:** Persist each critic report to `.tickets/XXXX-<slug>/critic-findings.md`
(append per round, mirroring `gate-findings.md`), commit it with the repair round on the
branch. Then: `/deliver` Step 5 scans it; `/review` and `/debug` read it; the delivery squash
archives it as a permanent record.

### A5 · MED — Escalation root-cause analysis is discarded; failure memory only learns from successes

`repair-escalation.md` Phase 1 spawns a diagnostic subagent that produces the highest-value
artifact in the whole failure path (root cause, failed strategies, fix strategy) — and never
records it. Meanwhile `build-ticket.md` Step 4e records to `memory` **only on pass**
(step 4: "If pass: call memory(record, outcome='passed')"); the `escalated` outcome that
`memory.py` supports is never written by the ticket flow. The BM25 memory therefore contains
only success narratives — `retrieve` can't warn a future repair away from approaches that
already failed.

**Fix:** (1) In Step 4e, also record after `MAX_REPAIR_ATTEMPTS` failures with
`outcome="escalated"`. (2) At the end of repair-escalation (both outcomes), record the
diagnostic subagent's root cause + strategy verbatim via `memory(action="record")`, and write
it into `critic-findings.md` (A4) so `/deliver` Step 5 can surface it as a candidate learning.

### A6 · MED — `/problem` Phase 6 is titled "Spec Score Check" but performs none

`commands/problem.md` Phase 6 body is one sentence: "Present Checkpoint 1 once the critic
loop is complete." The score-spec gate first runs at `/build`/`/write-spec` time — so a
structurally deficient spec sails through Checkpoint 1, gets approved by the lead, and then
BLOCKs at build time (in autopilot, triggering the Step S remediation machinery for artifacts
that were reviewable a phase earlier).

**Fix:** Make Phase 6 actually apply `context/score-spec.md` against the worktree artifacts
and include the verdict line in the Checkpoint 1 summary. BLOCKs get fixed *before* the lead
sees the checkpoint — strictly fewer human touches, and Step S becomes a rare path.

### A7 · MED — score-spec checks form, not substance

All six checks are structural (FR count, "must/shall" keyword, table cross-refs,
placeholders). A vacuous FR — "3. The system must work correctly" — passes every check.
Since the same artifacts drive spec generation, weak FRs propagate into weak acceptance
criteria and weak tests.

**Fix:** Add a WARN-tier LLM-judged rubric to score-spec (run by the model executing the
flow, no new subagent): for each FR, "could you write a *failing test* from this sentence
alone?" — report per-FR verdicts. Keep BLOCK purely structural (deterministic, non-flaky);
the rubric result feeds `/refine`-style autonomous tightening in Step S's semantic bucket.

### A8 · MED — No dependency/vulnerability gate for three of four languages, and no coverage signal anywhere

The pipeline's security floor is bandit-medium (Python only). TypeScript has no security
lint and no `npm audit`; Go has no `gosec`/`govulncheck` in any mode; Rust has `cargo-audit`
in text mode only (dropped in directory mode — `gates/rust.py:202-212` — the mode `/build`
actually uses). There is also no coverage measurement at all, so "requirements have tests" is
enforced solely by LLM judgement (critic Step 2.5).

**Fix:** (1) Add per-language WARN-tier audit gates in directory mode: `pip-audit`,
`npm audit --omit dev`, `govulncheck ./...`, `cargo audit` — surfaced in `gate-findings.md`
for the critic, BLOCK only on known-exploitable/critical. (2) Add a diff-coverage gate:
run tests with coverage, compute coverage of *changed lines* (e.g. `diff-cover`,
`go test -coverprofile` + filter, `cargo llvm-cov`), fail below a floor (e.g. 70–80%) —
this converts A2's "tests exist" from opinion to arithmetic. (3) Optional autopilot-only
depth: a fast mutation sample on changed files (`mutmut --paths-to-mutate`, Stryker
incremental, `cargo-mutants -F`) as a WARN gate; autopilot's wall-clock budget tolerates it.

### A9 · LOW — `/deliver` trusts a possibly-stale green

`deliver-ticket.md` never re-runs gates ("the diff was already reviewed"). In autopilot the
gap between last gate run and merge is seconds; interactively it can be days (and Step 7's
post-delivery rebases explicitly note "gates are invalidated" for *other* tickets without
re-running them). **Fix:** deliver Step 1 runs `gate_run_on_dir(worktree, "auto",
project_root)` fail-fast as a precondition; Step 7 re-runs gates on each successfully rebased
worktree and only downgrades to `implementing` on failure. Deterministic, zero human cost.

### A10 · LOW — Stale checkpoints survive spec edits

`checkpoint` stores completed spec IDs with no fingerprint. `/debug` Class A/B explicitly
proposes *editing the spec* and re-running `/build` — but Step 3/4a will skip the edited spec
("✓ already passed") because its ID is unchanged. **Fix:** store a content hash of each spec
file in the checkpoint; on mismatch, treat as not-completed.

### A11 · LOW — Autopilot runs the whole pipeline in one context

`/problem` ends by telling the lead to `/clear` before build "to keep implementation context
lean" — but `/autopilot` chains spec-gen → build → N critic/repair rounds → escalation →
deliver in a single session. On large tickets the repair rounds arrive exactly when the
context is fullest. **Fix:** note in `autopilot-ticket.md` that Steps 1–7c may be delegated
to a subagent per DAG layer (checkpoint + branch commits already make this resumable), or at
minimum instruct the model to keep gate output summaries, not full transcripts, in context.

---

## B. Deterministic machinery (gates, hooks, memory)

### B1 · HIGH — `pre_write_guard` suppression markers are a self-service bypass

(Also A2 item 2.) Any line matching a forbidden pattern is allowed through if it carries
`nosec` / `nolint` / `eslint-disable` / `@ts-expect-error` / `# noqa` (`pre_write_guard.py:47`).
The agent being guarded can add the marker itself, and no downstream check counts or reviews
suppressions. **Fix:** require a reason suffix, emit an advisory line (exit 0) even when
justified so it lands in the transcript, and have `stop_full_gate` fail on net-new
unexplained suppressions in the branch diff.

### B2 · HIGH — TypeScript test gate skips unchanged tests → regressions pass

`gates/typescript.py:335-346`: directory-mode Jest runs **only** the ticket's changed
`*.test.ts` files when git scoping succeeds. An implementation change that breaks an
untouched existing test passes the gate — precisely the regression class gates exist to
catch. The comment frames `None` → full suite as "fail closed", but a *successful* scoping is
the fail-open case. Python/Go/Rust dir gates run full suites, so TS is silently held to a
lower bar. **Fix:** run the full suite; if the motivation was pre-existing unrelated
failures, implement baseline-delta gating instead (run full suite on `main` merge-base once,
cache failing IDs, fail only on *new* failures) — deterministic and regression-safe.

### B3 · MED — `auto` detection: unsupported stacks get no real gating; Go missed in subdirs

`server.py:_detect_language` defaults to `"python"` for anything unrecognized (Java, C#,
Ruby, PHP, shell-only, SQL-only worktrees) — producing confusing mypy/pytest TOOL_ERRORs
rather than honest "unsupported" output. Worse, `hooks/stop_full_gate.py:detect_stacks`
returns `[]` for those worktrees → the Stop hook passes **silently** with zero enforcement.
Also `_detect_stacks` (`server.py:125-145`) checks `*/Cargo.toml` and `*/package.json` one
level down but only root `go.mod` — a Go service in `api/` is missed in a polyglot worktree;
and `any(d.rglob("*.py"))` will descend into `node_modules`/`.venv` and can misclassify a JS
project as Python. **Fix:** return an explicit `{"error": "unsupported stacks: [...]"}`
verdict (fail closed, honest message); add `*/go.mod`; exclude vendored dirs from the `.py`
scan; have the Stop hook print a one-line "no gate coverage for this worktree" warning
instead of silence.

### B4 · MED — Tools that aren't installed silently pass

- `gates/go.py:100-101`: staticcheck missing → `passed=True, duration_ms=0`.
- `gates/rust.py:157-159`: cargo-audit missing → same.
- `hooks/stop_full_gate.py:run_gate:122-123`: **any** missing executable → `(0, "")` — on a
  machine without ruff/mypy/pytest/eslint the entire Stop-hook layer is a no-op with no
  trace.

The gate layer's own invariant ("no silent failure", `gates/__init__.py:append_tool_error_if_silent`)
is not applied to the *skip* path. **Fix:** emit a `TOOL_SKIPPED` warning entry in the
GateResult (non-fatal but visible in `gate-findings.md`), and add an environment preflight to
`/init` (and optionally `build-ticket.md` Step 1) that lists which gates will actually run
for the detected stacks — turning "quietly weaker" into a one-time visible fact.

### B5 · MED — Gate configs override stricter project configs and are dated

- Python lint: hardcoded `--select E,F,W,I --ignore E501` (`gates/python.py:208-210, 328-330`)
  *overrides* a project's own ruff config — a project that enables `B` (bugbear), `S`
  (security), `UP`, `SIM` gets *weaker* gating inside the harness than in its own CI. Fix:
  if `ruff.toml`/`pyproject [tool.ruff]` exists, run bare `ruff check .`; keep the hardcoded
  floor only as fallback. Consider adding `B` and `S` to the floor.
- mypy always gets `--ignore-missing-imports` — hides wrong import paths, a common
  generated-code failure. Use it in text mode (temp dir, fair) but drop it in directory mode
  where the real environment exists.
- Text-mode env pins are stale for 2026 codegen: `go 1.21` (`gates/go.py:14`), Rust
  `edition = "2021"` (`gates/rust.py:15-26`), TS `target ES2020`/`commonjs`
  (`gates/typescript.py:16-30`) — generated code legitimately using newer language features
  fails the temp-env gate for the wrong reason. Bump, or detect from the host project.
- TS lint invocation uses legacy config (`.eslintrc.json`, `--no-eslintrc`, and dir-mode
  `--ext` at `typescript.py:321`) — all removed in ESLint v9 flat config. On a current
  ESLint, every dir-mode lint run exits with TOOL_ERROR (fail-closed but blocks all TS
  builds until someone diagnoses it). Ship a flat-config fallback.

### B6 · LOW — Hook/gate drift for the same language

The Stop hook and the MCP gates enforce different things: hook Go tests run without `-race`
(`stop_full_gate.py:271`) while the MCP gate uses `-race`; hook Python mypy runs on changed
files only, MCP gate on the whole dir; `post_write_gate.py:65` invokes bare `eslint` from
PATH (almost never present — projects install it locally), whereas the Stop hook correctly
uses `npx --no-install`. Result: the per-write JS lint check essentially never fires. Align
each hook command with its MCP-gate counterpart.

### B7 · LOW — Memory hygiene

`memory.py` has no pruning or staleness policy (retrieval window is "300 most recent per
gate", so old-but-recurring lessons age out invisibly), and narratives don't include the
resolution — only the error text — so a retrieved "✓ passed" record tells the repairer a
similar failure was fixed but not *how*. Consider recording a one-line `resolution` field at
`memory(action="record", outcome="passed")` time (the fix diff summary is in context at that
moment) — this is the single change that would most improve retrieval usefulness.

---

## C. /critique expert-panel workflow

The panel corpus is genuinely strong: current (Willison's lethal trifecta, Hyrum's Law,
prompt-caching, ESLint-era hazards), opinionated with named disagreements, and the
severity/output discipline in `skills/critique/SKILL.md` is unusually well specified. The
findings below are gaps, not weaknesses in what exists.

### C1 · MED — Coverage gaps in the panel roster

No panel exists for several domains the trigger table can already encounter:

- **.NET/C#** — no panel, no gate, not even a trigger row; a C# worktree activates Core only.
- **GraphQL** — schema design, N+1 resolvers, auth-per-field; common enough to warrant a row
  (trigger: `*.graphql`, `graphql`/`apollo` in manifests).
- **Protobuf/gRPC** — `.proto` files, wire-compat rules (field renumbering, required→optional),
  deadline/retry semantics. Currently matches nothing.
- **Mobile** (Swift/SwiftUI, Kotlin-Android beyond JVM generics) — Kotlin hits the JVM panel,
  which has no Android/lifecycle content; Swift matches nothing.
- **Accessibility** is folded into UI — adequate for markup, but there is no WCAG-focused
  lens for interactive-widget semantics (focus management, ARIA states) that a UI panel
  skim tends to under-weight.
- **Secrets/supply-chain** — cicd.md exists, but pinning (lockfile discipline, action SHA
  pinning, provenance/SLSA) deserves explicit hazard rows if it isn't already there.

Adding even thin (40-line) panels for GraphQL, proto/gRPC, and .NET removes the silent
Core-only fallback for those stacks.

### C2 · MED — Panel-header activation text has drifted from the trigger table

`context/panels/python.md:3` says *"Active when `app/**/*.py` or `tests/**/*.py` files are in
scope"* while the authoritative table (`skills/critique/SKILL.md` Step 1) says any `**/*.py`
or Python manifest. Since the SKILL table is declared the single source of truth
(`critic-brief.md` Step 1), stale per-panel headers are a live confusion source for the
critic subagent, which reads both. Sweep all panel headers and either delete the activation
sentence or replace it with "Activation: see the trigger table in skills/critique/SKILL.md."

### C3 · MED — Panel findings have no lifecycle

`/critique` writes `CRITIQUE.md` **in the current working directory** with a fixed name:
successive critiques overwrite each other, the file lands wherever the session happens to be
(potentially inside a worktree, where the next `git add .` in `build-ticket.md` Step 5 will
commit it into the delivery squash), and nothing downstream (memory, `/deliver` learnings,
future `/problem` runs) ever reads it. **Fix:** write to
`.harness/critiques/<target-slug>-<date>.md` (git-ignored alongside results/), and mention
recent critique files in `/status` output; if the critique targeted a ticket's files, also
append a pointer line into that ticket's `critic-findings.md` (A4).

### C4 · LOW — Undefined operational terms

Two panel-machinery rules have no operational definition: the Secondary panel loads "only
when the primary panels reach a genuine impasse synthesis cannot resolve"
(`SKILL.md` Step 2 / `critic-brief.md`) — impasse is never defined, so the panel either
never loads or loads on vibes; and ">5 panels → prioritize findings by severity across
panels" gives no budget (e.g. "cap total findings at N; drop OBS first"). One sentence each
would make both deterministic.

### C5 · LOW — Three parallel descriptions of one review procedure

The critique skill, review skill, and critic-brief each restate panel loading, severity
tiers, and the read-everything-first rule. They currently agree (good), but they will drift —
C2 is the existing example of exactly this failure mode, and the round-cap contradiction (A3)
is another. Consider making `critic-brief.md` the only place the procedure lives, with the
two skills holding only their interaction-shape deltas (interactive staging, output
destination, status transition).

### C6 · LOW — Design-mode critic reviews artifacts written by its own parent

In `/problem` Phase 5 the same session that authored `solution.md` spawns the critic and then
*applies the critic's findings itself*. The critic subagent is fresh-context (good), but the
revision step is not — the author revises to satisfy the reviewer, and round 2 (if any) is
the only verification. Cheap hardening: have round 2 be mandatory whenever round 1 produced
any BLOCKER (currently "if significant issues were raised", undefined), and require the
Checkpoint-1 summary to quote the residual finding counts rather than "how resolved" prose.

---

## D. Prioritized action list

| # | Ref | Action | Effort |
|---|-----|--------|--------|
| 1 | A1 | Worktree-first resolution rule + fix 4 flows committing post-claim state to main | S–M |
| 2 | A2/B1 | Repair-integrity check (test deletion / suppression pragmas) + reasoned-suppression rule | M |
| 3 | B2 | Full Jest suite (or baseline-delta gating) in TS dir mode | S |
| 4 | A4/A5 | Persist critic reports + escalation diagnoses; record `escalated` outcomes to memory | S |
| 5 | B4 | TOOL_SKIPPED warnings + `/init` gate preflight | S |
| 6 | A3 | Fix critic round-cap wording | XS |
| 7 | A6 | Make `/problem` Phase 6 actually run score-spec | XS |
| 8 | A8 | Dependency-audit gates (pip-audit / npm audit / govulncheck / cargo-audit in dir mode) + diff-coverage gate | M |
| 9 | B5 | Respect project ruff/eslint configs; flat-config ESLint; bump go/rust/ts env pins | M |
| 10 | B3 | Honest unsupported-stack verdict; `*/go.mod`; vendored-dir exclusion | S |
| 11 | C1/C2 | GraphQL + proto/gRPC + .NET panels; sweep stale panel activation headers | M |
| 12 | C3 | Critique output to `.harness/critiques/`, not cwd `CRITIQUE.md` | XS |
| 13 | A7 | WARN-tier testability rubric in score-spec | S |
| 14 | A9/A10 | Gate re-run at deliver + post-rebase; spec-hash checkpoint invalidation | S |
| 15 | B6/B7 | Align hook commands with MCP gates; add `resolution` field to memory records | S |

---

## What already works well (keep)

- **Fail-closed discipline in the gate results model** — `append_tool_error_if_silent` and
  the "passed=False must never have empty errors" invariant are exactly right; the fix list
  above mostly *extends* this philosophy to skip-paths and hooks.
- **Autopilot's bounded-autonomy design** — Step S's mechanical/semantic/hard-stop
  classification with a hard budget, and the refine-touched carve-out (machine-adjusted scope
  never merges unseen) is a genuinely well-thought-out autonomy boundary.
- **The panel corpus** — named experts with real positions and named disagreements
  (Martin vs Ousterhout, Dodds vs Feathers), current-as-of-2026 content (lethal trifecta,
  Hyrum's Law, prompt caching, LLM-as-judge calibration), and the split-independent-findings
  rule (SKILL.md rule 11) which directly prevents remediation-scope loss.
- **Two-layer learning split** — machine BM25 memory vs lead-curated `_learnings.md`, with
  the harness never writing the human layer. Right call; A5 just asks the machine layer to
  learn from failures too.
- **The squash-delivery invariant** and `ticket_commit_guard`'s worktree-aware scan.

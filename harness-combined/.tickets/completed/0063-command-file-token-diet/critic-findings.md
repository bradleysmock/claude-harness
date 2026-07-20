## Round 1 — 2026-07-20

## Critic Report — Round 1 (code phase)

**Ticket**: 0063-command-file-token-diet
**Active panels**: Core (only — all four files in scope are markdown command/flow docs; no language, framework, security, or infra trigger in the critique trigger table matches non-code documentation content beyond Core)

**Scope reviewed**: `commands/problem.md`, `context/harness-reference.md`, `context/flows/build-ticket.md`, `context/flows/repair-escalation.md` (full files), cross-checked against `ticket_templates.py` and `ticket_deps.py` (`assert_acyclic_with_proposed`) for docstring-pointer accuracy, and against `.tickets/0063-command-file-token-diet/{problem,requirements,solution}.md`.

### Requirements coverage (Step 2.5)

All six functional requirements are satisfied:

- FR-1/FR-2 (`commands/problem.md:50-84`, `:259-281`): Phase 1.5's five numbered calls each state what the helper does and defer "how" to the named `ticket_templates.py` docstring; the dependency-cycle-check block keeps the code snippet and defers to `assert_acyclic_with_proposed`'s docstring. Cross-checked every named function (`validate_type`, `infer_category`, `load_template`, `load_custom_sections`, `merge_sections`, `enforce_line_limit`, `format_type_field` in `ticket_templates.py`; `assert_acyclic_with_proposed` in `ticket_deps.py`) — all real, and the summarized behavior (allow-list categories, additive-only fallback, per-artifact injection targets — template into `problem.md` only vs. custom sections into all three, `ValueError`/`TicketCyclicDependencyError` split) matches each docstring exactly.
- FR-3 (`context/harness-reference.md:433-449`): single canonical persistence block added, extending the existing "Critic findings file" subsection without disturbing its pre-existing bullets (append-only, per-finding marker, committed-on-branch, consumed-downstream, memory.db counterpart — all untouched from ticket 0062's version).
- FR-4 (`build-ticket.md:243`, `:268`; `repair-escalation.md:29`, `:59`, `:82`): all 5 sites reference the canonical block and state only their own `<section-heading>`/`<commit-message>` variance. The repair-escalation.md diagnosis site (`:29`) correctly preserves the level-3-heading rationale (`### Escalation diagnosis`, not `## `, to avoid shadowing `critic_reconciler.latest_section()`'s round-boundary scoping) inline before pointing at the canonical block.
- FR-5: behavior appears unchanged — every site still names its write target, commit message, and (where relevant) the marker-embedding/reconcile steps from ticket 0062, which are fully intact and consistent across `build-ticket.md` Step 7/7a and both `repair-escalation.md` phases (same `gates.critic_finding_parser`, `gates.critic_reconciler.harvest_keys/latest_section/marker_for_key/reconcile`, `gates.finding.finding_key` calls, same reconcile-before-persist ordering).
- FR-6: no `.py` file in this worktree was modified; only docstrings were read for cross-reference.

No requirements-coverage gaps found.

### Solution alignment

Matches `solution.md`'s Components/Tech Choices tables directly — placeholder-parameterized single canonical block, docstring-pointer conversion in `problem.md`, and the "extend existing section" tech choice were all followed as designed.

### Findings

No BLOCKER, MAJOR, or MINOR findings.

- **OBS** — `context/harness-reference.md:440-443`. The new canonical persistence pattern's git snippet shows `add` + `commit` for the `critic-findings.md` append but no explicit `push`. This is consistent with the sibling snippets already in these two files (`build-ticket.md:204-206` Step 5 commit, `:215-217` Step 6 status commit, `:266` Step 7a fix commit — none show an explicit push either), so it is not a regression introduced by this ticket. Worth the lead confirming, separately from this ticket, whether branch-push timing for these commits is intentionally deferred to a later point in the flow or is a latent gap in the docs generally.
- **OBS** — `commands/problem.md:259-266`. The dependency-cycle-check section retains a full explanatory paragraph on why the *proposed* edge (not just on-disk state) must be validated before the `depends-on:` write, which is more than requirements.md FR-2's literal "one-line pointer" phrasing. It does not restate `assert_acyclic_with_proposed`'s internal validation logic (that's correctly deferred to the docstring pointer at `:278-281`), so this reads as a reasonable orientation-preserving judgment call consistent with the ticket's own stated risk mitigation ("keep a 1-line 'what' … not just a bare pointer"), not a defect.

No accidental scope creep or merge-conflict damage against ticket 0062's finding-key/reconcile machinery was found — the marker/reconcile logic reads as intact and correctly interleaved with this ticket's reference-based shortening at every one of the 5 call sites.

# Test-Retrofit Prompt Sequence

A phase-by-phase prompt chain for an orchestrated agent retrofitting a test suite onto an untested codebase. Designed for a multi-role harness: a **generator** role produces artifacts, a **verifier** role critiques them adversarially. Each phase emits a structured artifact that becomes input to the next.

**Placeholders:** `{repo}` repo root · `{lang}` language · `{N}` history window in months · `{kill_target}` mutation-score threshold (start 0.75).

**The thread running through all phases:** keep *recording current behavior* and *asserting intended behavior* strictly separate. Characterization tests pin what the code does (bugs included); only the unit/contract phases assert what it *should* do, and those assertions must come from an external oracle — never inferred from the code under test.

---

## Phase 0 — Reconnaissance & Seam Detection

**Role:** generator (analysis only — no test code).
**Input:** `{repo}`.

A *seam* (Feathers) is a place where you can alter behavior without editing in that place. The point of this phase is not to write tests but to discover where tests can attach and what currently blocks them.

```
Analyze the codebase at {repo}. Do NOT write tests. Produce a seam map.

For each public unit (function/method/class) in the core modules:
1. List every collaborator it invokes and classify each as:
   - PURE (deterministic, no side effects) — directly testable
   - I/O / SIDE-EFFECTING (network, filesystem, DB, clock, randomness,
     env, global mutable state) — requires a seam
   - HIDDEN dependency (static/singleton call, ambient global, implicit
     construction) — blocks testing until surfaced
2. For each non-pure collaborator, identify the substitution mechanism
   and its refactor cost:
   - INJECTABLE (already passed via constructor/parameter) — cost: none
   - MODULE-MOCKABLE (substitutable at import/link boundary) — cost: low
   - REQUIRES-REFACTOR (must extract an interface, parameterize a
     dependency, or break a static call before it can be substituted)
     — cost: medium/high, describe the specific change
3. Flag ENABLING POINTS: single refactors that unlock testing for many
   units at once (e.g. injecting one clock, breaking one singleton).

Output as a table: unit | collaborators | dependency class | seam type |
substitution mechanism | refactor cost | enabling-point (y/n).
Also list the {lang}-idiomatic seam techniques available here
(e.g. DI, interface extraction, module mocking, link substitution).
```

**Output contract:** `seam-map.md` (the table) + an enabling-points shortlist.
**Verifier gate:** challenge every `cost: none` claim — does the dependency *actually* arrive through a substitutable channel, or is it constructed internally? Confirm no hidden static/global dependency was misfiled as pure. The map is wrong until the verifier signs off, because everything downstream trusts it.

---

## Phase 1 — Infrastructure & Smoke Test

**Role:** generator.
**Input:** `seam-map.md`.

Prove the full loop closes before generating volume.

```
Stand up the test harness for {lang} at {repo}:
- Choose runner, assertion library, mocking/fixture strategy
  (justify each in one line).
- Configure coverage instrumentation AND wire mutation-testing tooling
  now, even though it runs later: {lang} → PIT (JVM) / Stryker (JS/TS) /
  mutmut or cosmic-ray (Python) / go-mutesting (Go).
- Write exactly ONE trivial smoke test against a pure unit from the
  seam map.
- Wire runner + coverage into CI as a gating check.

Deliver the config, the one test, and proof the CI job runs green.
Do not write any further tests.
```

**Exit gate:** CI green on one test; coverage report emitted; mutation tool installed and runnable on a single file. Discovering infrastructure problems now is cheap; discovering them after 300 tests is not.

---

## Phase 2 — Risk Prioritization

**Role:** generator, using git history as objective signal.
**Input:** `seam-map.md` + `{repo}` git log.

Rank what to test first. Coverage percentage is a lagging vanity metric; risk is the real ordering function.

```
Build a risk-ranked test backlog for {repo}. Use git as data — run the
commands, don't estimate.

Per module, compute:
- CHURN: commit count and lines changed over the last {N} months
  (git log --numstat --since).
- BLAST RADIUS: fan-in / number of dependents (static import graph);
  note modules with high centrality.
- COMPLEXITY: cyclomatic complexity (use a {lang} analyzer).
- DEFECT SIGNAL: density of bug-fix commits touching the file
  (filter messages: fix|bug|hotfix|patch|revert).
- AMBIGUITY: from the seam map, how much behavior is currently
  unpinned and how hard it is to predict.

Score = normalize and combine (churn × blast_radius) weighted up,
complexity and defect_signal as multipliers. Output a ranked table:
module | churn | fan-in | complexity | defect signal | seam cost
(from Phase 0) | score | rationale.

Then split the ranking into waves. CRITICAL CONSTRAINT: do NOT
deprioritize a module merely because its seam cost is high. High-risk +
hard-to-test is the most important quadrant — surface it explicitly as
"refactor-then-test," never as "skip."
```

**Output contract:** `risk-backlog.md` with waves: Wave 1 = high-risk + low seam-cost (fast wins), Wave 2 = high-risk + high seam-cost (refactor-then-test), Wave 3 = the long tail.
**Verifier gate:** sanity-check the score against intuition — if a module everyone fears ranks low, the weighting or the git filter is wrong. Confirm no high-risk module was buried because it's painful to test.

---

## Phase 3 — Characterization Layer (pin current behavior)

**Role:** generator.
**Input:** Wave 1/2 modules, at the stable seams from Phase 0.

```
For the modules in {wave}, generate characterization tests at the
stable interface seams. These RECORD current observable behavior to
serve as a refactoring net — they do NOT assert correctness.

- Test through the seam, not internal implementation details.
- For each unit, capture representative inputs incl. boundaries and
  error paths; assert on the behavior currently produced.
- Where current output is surprising, DO NOT "fix" it in the assertion.
  Record it as-is and add a // CHARACTERIZED: possibly-incorrect marker
  with a one-line note for human review.
- Header every file: "Characterization tests — record current behavior,
  not validated correctness."
```

**Exit gate:** the net is green against unmodified code. Every `possibly-incorrect` marker is logged for the oracle review in Phase 4 — these are candidate bugs, not test failures.

---

## Phase 4 — Refactor & Unit Tests (assert intended behavior)

**Role:** generator for refactor + tests; **human/spec oracle** for assertions.
**Input:** characterization net (as safety), enabling points, `possibly-incorrect` log.

This is the only phase where assertions encode *correctness*, so this is the only phase where assertions may not be inferred from the code.

```
Under the protection of the characterization net:
1. Apply the enabling-point refactors from Phase 0 to make target units
   testable (extract interfaces, inject the clock/RNG/IO, break
   singletons). The net must stay green throughout; if behavior must
   change, stop and flag it.
2. Write focused unit tests for the refactored units. For every
   assertion, cite its ORACLE: the human-provided spec, documentation,
   ticket, or contract it derives from. Any assertion you cannot tie to
   an external oracle must be marked UNSOURCED for human confirmation —
   do not invent intended behavior from the implementation.
3. Resolve each CHARACTERIZED: possibly-incorrect marker: confirm the
   behavior is intended (promote to a real assertion) or file it as a
   bug.
```

**Human gate:** review targets the *assertions and their oracles*, not whether the suite passes. A green suite of self-derived assertions is the central failure mode of LLM-generated tests — it certifies the code does what it does.

---

## Phase 5 — Contract Tests at Seams

**Role:** generator.
**Input:** module/service boundaries from Phase 0.

```
At each module or service boundary identified as a seam, write contract
tests that lock the interface: input acceptance, output shape, error
contract, and invariants the consumer relies on. These protect the
boundary independently of either side's internals. For cross-service
seams, structure them as consumer-driven contracts.
```

**Exit gate:** boundaries are pinned; internal refactors on either side can't silently break consumers.

---

## Phase 6 — Mutation Testing (the quality gate)

**Role:** **verifier** generates targeted kills against the **generator's** tests — the adversarial loop, with mutation score as the objective fitness function. Coverage proves a line *executed*; mutation testing proves a test would *catch a fault in it*. It is the only gate that detects tautological tests (everything mocked, nothing asserted).

```
Run mutation testing scoped to {module} (NOT the whole repo — scope to
changed files for tractable runtime; in CI, run on the diff).

Tool: PIT / Stryker / mutmut / cosmic-ray per {lang}.

From the report:
1. Compute mutation score = killed / (total − equivalent).
2. For each SURVIVING mutant, emit a concrete remediation task:
   "mutant at {file}:{line} ({operator}, e.g. conditional-boundary,
   negate-conditional, return-value) survived — write or strengthen an
   assertion that distinguishes original from mutant."
3. Hand survivors to the generator role; it writes targeted tests.
   Re-run. Loop until mutation score ≥ {kill_target} OR every remaining
   survivor is justified as an EQUIVALENT mutant (semantically identical
   to the original — unkillable). Mark equivalents explicitly and cap
   effort on them; do not chase 100%.

Report: mutation score, killed/survived/equivalent counts, and the
remediation tasks generated this round.
```

**Why this catches what coverage misses:** a file can hit 100% line coverage with a low mutation score — the tests run the code but assert nothing meaningful. Surviving mutants are precise, actionable gaps, not a vague percentage. Feed them back through the generator/verifier loop and the suite's fault-detection improves measurably each round.

**Exit gate:** `{kill_target}` met on the module, or remaining survivors documented as equivalent.

---

## Orchestration Spec

### Roles

- **Orchestrator (O)** — owns the per-module state machine; schedules phases, routes artifacts, enforces gates, handles escalation. Never writes or judges tests. Deterministic glue.
- **Generator (G)** — produces analysis and test code. Optimizes for the task; assumed to be a biased judge of its own output.
- **Verifier (V)** — adversarial critic. Owns static gates, interprets execution signals, justifies equivalent mutants. Never accepts G's self-report. Should be a distinct model or at minimum a distinct context from G, so blind spots don't transfer.
- **Executor (X)** — non-LLM tooling: test runner, coverage, mutation engine, git, complexity analyzer. The only source of model-independent verdicts; its gates can't be reasoned around.
- **Human Oracle (H)** — owns correctness/intended-behavior judgment and exactly two cheap touchpoints (seam-map sign-off, assertion/oracle review).

### Handoff contract

Each phase consumes a typed artifact and emits one. A handoff completes only when its gate predicate holds; the gate *owner* is whoever can evaluate the predicate without trusting the producer.

| Phase | Producer | Consumes | Produces | Gate owner | Gate predicate |
|---|---|---|---|---|---|
| 0 Seam | G | repo | `seam-map.md` | V → H | No dep misclassified pure; every "no-refactor" claim verified; H signs off |
| 1 Infra | G | seam-map | harness + 1 smoke test | X | CI green; coverage emitted; mutation engine runs on one file |
| 2 Risk | G + X(git) | seam-map | `risk-backlog.md` (waves) | V | Ranking matches evidence; no high-risk module buried for seam cost |
| 3 Characterization | G | wave modules | frozen char-net | X | Net green vs **unmodified** source; net then immutable |
| 4 Refactor+Unit | G | char-net, enabling points | refactors + unit tests | X → H | Char-net stays green; every assertion oracle-cited; `possibly-incorrect` markers resolved |
| 5 Contract | G | seam boundaries | contract tests | X → V | Green; covers shape, error contract, invariants |
| 6 Mutation | X + V↔G loop | unit/contract tests | mutation score + kills | X + V | score ≥ `{kill_target}` OR all survivors justified equivalent |

### Adversarial loop (Phases 4-gate and 6)

Phase 6 is a fixpoint loop, not a single pass:

```
loop:
  report   = X.mutation_test(module)          # deterministic signal
  if report.score >= kill_target: break
  survivors = report.survivors
  tasks     = V.triage(survivors)             # each → a concrete kill task
  G.write_kills(tasks)                         # generator answers the critic
  iterations += 1
  if iterations > MAX_ITERS:                   # default 4
    O.escalate(H, survivor_report); break
# remaining survivors must be V-justified as equivalent, else block
```

Two invariants the orchestrator enforces:
- **Net immutability** — once the Phase 3 char-net is green it is frozen. Any Phase 4 source edit that turns it red is a halt, not a test-fix. The net is the contract that refactoring preserved behavior.
- **No self-grading** — G never evaluates its own gate. Scores come from X; triage and equivalence judgments come from V; correctness comes from H.

### Shared state manifest

One record per module, owned by O, updated at every handoff:

```yaml
module: payments/ledger
phase: 6
status: in_progress        # pending|in_progress|gated|blocked|done
artifacts:
  seam_map: seam-map.md#ledger
  char_net: tests/char/ledger_char_test.*   # frozen: true
  unit:     tests/unit/ledger_test.*
gates:
  seam:    {owner: V, passed: true, human_signoff: true}
  net:     {owner: X, green: true, frozen: true}
  oracle:  {owner: H, unsourced_assertions: 0, possibly_incorrect_open: 1}
mutation: {score: 0.71, target: 0.75, iterations: 3, equivalent: 2}
blockers: ["possibly-incorrect@ledger.rebate: awaiting H ruling"]
```

### Concurrency & sequencing

- Modules flow through the pipeline in parallel, but each module is **sequential** through its phases.
- Wave ordering from the risk backlog is a scheduling constraint: at least the Wave 1 modules must reach a passing Phase 6 before Wave 3 begins. You want the highest-risk code fully gated early, not the whole repo stuck at one phase.
- Optimize the harness against one number only: **mutation score on risk-ranked modules.** Never coverage, never test count.

### Escalation / halt rules

| Condition | Action |
|---|---|
| Char-net red after a Phase 4 edit | Halt module; surface diff to H — behavior changed under refactor |
| Assertion cannot be oracle-sourced | Block at Phase 4 gate; H confirms intended behavior or files bug |
| Mutation loop exceeds `MAX_ITERS` | Escalate survivor report to H; do not fabricate kills to hit the number |
| V flags a survivor as non-equivalent that G can't kill | Block; likely a missing seam — return to Phase 0 for that unit |

---

## Test-Quality Assessment Prompts

These operationalize the two-axis model: **fault detection** (does the test catch deviations — answerable by execution) and **oracle validity** (does it assert the *correct* behavior — answerable only by H). Q1–Q3 and Q6 run agent-side; Q4–Q5 are execution probes; the scorecard keeps the two axes from collapsing into one gameable figure.

### Q1 — Static smell audit (Verifier, no execution)

Necessary but insufficient, and it shares the author's blind spots — treat as a floor, not a verdict.

```
Review the tests for {module}. Do not run them. For each test, flag any:
- NO-ASSERTION: passes if nothing throws; asserts no value.
- WEAK ASSERTION: asserts type/non-null/truthiness, not the specific
  expected value.
- TAUTOLOGY: collaborators so mocked that the test only verifies a mock
  was called — no real behavior exercised.
- CHANGE-DETECTOR: asserts on internal structure/call order/private
  state; would break under a behavior-preserving refactor while catching
  no bug.
- HAPPY-PATH-ONLY: no boundary, error, or empty/extreme inputs.
- OVER-BROAD: assertion so loose it would pass for incorrect outputs.

Output: test id | smells | severity (block/warn/note) | one-line fix.
Do not certify quality — this pass only detects gross pathologies.
```

### Q2 — Mutation interpretation & gaming check (Verifier on Executor output)

```
Given the mutation report for {module}, produce:
1. Score = killed / (total − equivalent), and the coverage figure
   alongside it.
2. GAMING FLAG: if line coverage is high but mutation score is low, name
   it — the suite executes the code without meaningfully asserting on it.
3. Per surviving mutant: file:line, operator, and a concrete kill task
   ("add assertion distinguishing original from mutant").
4. Equivalence candidates: survivors you judge semantically identical to
   the original. Justify each in one sentence; unjustified survivors are
   NOT equivalent and remain open.
Never propose deleting or weakening a test to raise the score.
```

### Q3 — Oracle-provenance audit (Verifier pre-screen → Human ruling)

The half mutation testing cannot see. A test with a perfect kill rate can still pin a bug as correct.

```
For every correctness assertion in {module}'s unit tests, classify the
source of its expected value:
- EXTERNAL: traceable to a spec, ticket, doc, or human statement — cite it.
- CHARACTERIZED: recorded current behavior; makes no correctness claim.
- SELF-DERIVED: expected value inferred from the code under test itself.

Flag every SELF-DERIVED assertion presented as a correctness check —
these are circular and must be re-sourced or demoted to characterization.
Output a provenance table; route SELF-DERIVED and CHARACTERIZED-but-
asserted rows to H for a ruling.
```

### Q4 — Refactor-robustness probe (Executor + Generator)

Distinguishes behavioral tests from implementation mirrors.

```
Apply a known behavior-preserving transformation to {module} (rename
internals, reorder independent statements, extract a method, or inject a
verified-equivalent mutant). Re-run the suite.
- Tests that now FAIL are coupled to implementation, not behavior —
  report them as change-detectors with the triggering transformation.
Revert the transformation afterward. A robust test is indifferent to it.
```

### Q5 — Flakiness probe (Executor)

```
Run {module}'s suite N≥20 times with randomized test order and varied
seeds/clock. Report any test whose result is non-deterministic, with the
observed failure rate. Flaky tests have negative quality value — they
erode trust in the gate — and must be fixed or quarantined, not ignored.
```

### Q6 — Quality scorecard (Verifier roll-up)

The capstone. Refuses a single composite number on purpose.

```
Produce a quality verdict for {module} on two independent axes — do not
average them:

FAULT DETECTION (execution-grounded):
- mutation score vs {kill_target}
- assertion density (assertions per test; flag tests < 1)
- smell counts by severity (Q1)
- change-detector count (Q4)
- flakiness rate (Q5)

ORACLE VALIDITY (correctness-grounded):
- % assertions EXTERNAL vs SELF-DERIVED (Q3)
- open possibly-incorrect markers
- unresolved H rulings

Verdict: PASS only if fault detection meets thresholds AND oracle
validity has zero self-derived correctness claims and zero open H items.
State explicitly that strong fault detection does NOT compensate for weak
oracle validity — a sharp test asserting the wrong thing is still wrong.
```

---

## Sequencing (summary)

Run Phases 3→6 per risk wave, hardest-quadrant modules included, with the wave-ordering and net-immutability constraints above. The two decisive human touchpoints — Phase 0 seam-map sign-off and the Phase 3/4 oracle review (Q3) — are cheap and load-bearing; everything else runs agent-to-agent under X-owned gates. The harness's single fitness signal is mutation score on risk-ranked modules; the scorecard (Q6) exists to stop that signal from masquerading as a complete quality measure.

---

## Role-Assignment Matrix

### Principle: assign by the property the role actually needs

| Role | Dominant requirement | Cost exposure | Notes |
|---|---|---|---|
| **G** Generator | Strong agentic coding + instruction-following + long context | **High** — bulk of token volume | Route by module difficulty: a workhorse tier by default, top tier reserved for the Wave-2 refactor-then-test quadrant |
| **V** Verifier | Adversarial reasoning + code comprehension **+ independence from G** | Medium — runs per gate, not per line | The independence constraint is load-bearing. See below |
| **X** Executor | None — **not a model** | Compute only | Mutation engine, runner, coverage, git, complexity analyzer. Don't spend a model here; the intelligence is in *interpreting* X, which is V's job |
| **H** Human | Correctness judgment | Your time | Two touchpoints only: seam-map sign-off, oracle review (Q3) |

### The one decision that matters: V's independence

The no-self-grading guarantee is only as strong as the gap between G and V. Ranked best to worst:

1. **Different vendor family** — G and V drawn from different model families (e.g. G on one frontier family, V on another). Their training corpora and failure modes diverge, so V is least likely to inherit the exact blind spot that produced a weak test. This is the real version of the guarantee.
2. **Different tier, same vendor** — V a strictly stronger model than G within one family (e.g. G on the workhorse tier, V on the flagship), run in a clean context with an explicitly adversarial system prompt. Weaker: shared priors mean shared blind spots.
3. **Same model, different role prompt** — V and G the same model in different contexts. This is the *weakest* configuration and the likeliest state of a Claude-Code-only harness. It still catches gross pathologies but cannot be trusted to catch failures rooted in shared priors.

**Compensating move when V can't be independent:** weight execution-grounded signals (X: mutation score, Q4 refactor probe, Q5 flakiness) far above agent-side judgment (V: Q1 smells, Q2/Q3 triage). When you can't make the critic independent, make the *oracle* deterministic. Two same-family LLM instances agreeing tells you little; a surviving mutant tells you something true regardless of who's judging.

### Three configurations

**A — Maximum independence (recommended for the gate that protects correctness):**
- G: a frontier coding model (default tier).
- V: a frontier *reasoning* model from a **different vendor family**, high reasoning effort, clean context.
- X: language-native mutation + runner.
- Rationale: cross-family V on the seam-map gate (Phase 0) and mutation triage (Q2) gives genuine blind-spot diversity. The current frontier is competitive enough across families that this costs you little in raw capability.

**B — Single-vendor pragmatic (likely your current Claude-Code setup):**
- G: workhorse tier (e.g. Sonnet-class) for routine generation; flagship tier (e.g. Opus-class) for Wave-2 hard modules.
- V: flagship tier over G's workhorse output, separate session, adversarial prompt.
- X: same.
- Caveat: V and G share priors — this is config #2/#3 above. Lean on the compensating move; treat X as the real gate and V as a pre-filter.

**C — Cost-optimized at scale:**
- G: a strong, cheap open-weight coding model for high-volume routine generation; promote to frontier only when V or X bounces a module back.
- V: one frontier model, used sparingly at gates rather than per-test.
- X: unchanged — it's compute, and it's where your trust should concentrate anyway.
- Rationale: the price-to-capability floor has risen sharply; competent open-weight models now handle routine generation, letting you spend frontier budget only on verification and hard modules.

### Routing rule for G

Don't run one model for all generation. Drive G's tier from the Phase 2 risk score and Phase 0 seam cost: workhorse tier for low-risk / low-seam-cost units, flagship tier for the high-risk + high-seam-cost quadrant where refactor reasoning is hardest. The orchestrator already has both numbers in the state manifest — make tier selection a function of them.

### What never gets a model

X stays deterministic. The temptation is to let an LLM "judge" quality directly; resist it. Every quality verdict that can be grounded in execution (mutation, refactor-robustness, flakiness) should be, precisely because those are the signals no model — independent or not — can talk its way past.

---

## Verifier (V) System Prompt — Same-Family Hardening

Drop this in as V's system prompt when G and V are the same model family (config B). Its entire job is to counteract the shared-prior problem: a sibling model finds the same wrong things plausible, so the prompt forces V to treat its own intuition as compromised evidence and to settle disputes with execution rather than agreement.

```
ROLE
You are V, an adversarial test verifier. You did not write these tests and
you owe their author nothing. Your sole function is to find the ways this
suite fails to detect faults or asserts incorrect behavior. You do not
certify quality — you attempt to break the claim that the suite is adequate.
Default verdict is REJECT. PASS is earned only by surviving your attack.

THE COMPROMISED-INTUITION RULE — read before anything else
You are the same model family as the author. Every test that strikes you as
"obviously fine" struck the author the same way, for the same reasons. Your
sense of plausibility is correlated with the exact process that produced any
defect in front of you. Therefore your intuition is evidence of nothing. A
value that "looks right" is not verified — it is suspect precisely because it
looks right to you. When you notice yourself agreeing with the author, stop:
agreement is your least reliable signal, not a reason to approve.

INDEPENDENCE DISCIPLINE
- Never accept a plausible expected value as a sourced one. For every
  correctness assertion, demand a citation to an external oracle (spec,
  ticket, doc, human). If none exists, mark it UNSOURCED. Do NOT rescue it by
  re-deriving the value from the code under test — that reproduces the
  author's circular reasoning inside your own.
- When you must check an expected value, derive it from the specification
  independently. Do not read the implementation to decide what the output
  "should" be. The implementation is the thing on trial; it cannot be its own
  witness.
- Distrust fluent justification. A well-written rationale for a weak test is
  the most dangerous artifact you will see, because you are easily persuaded
  by reasoning that resembles your own. Where a claim can be settled by
  running something — a mutant, a refactor probe, a rerun — prose does not
  settle it. Demand the execution evidence.

FAILURE MODES TO HUNT (what a model like the author reliably gets wrong)
- CIRCULAR ASSERTION: expected value confirmable only by consulting the code
  under test. If you cannot source it elsewhere, it is unsourced, not correct.
- HAPPY-PATH BIAS: canonical case present; boundaries, empties, nulls,
  malformed input, error/exception paths, and concurrency absent. Models
  gravitate to the typical — treat their absence as the default failure.
- TAUTOLOGICAL MOCKING: collaborators mocked so thoroughly the test asserts
  only a mock's configured return or that a mock was called. No real behavior
  exercised.
- IMPLEMENTATION MIRRORING: assertions on internal structure, call order, or
  private state that restate the code's logic — change-detectors that break
  under behavior-preserving refactor while catching no bug.
- COVERAGE-SHAPED, NOT FAULT-SHAPED: lines execute but assertions are absent,
  weak (type / non-null / truthiness), or broad enough to pass for a wrong
  output.
- SYMMETRIC ORACLE ERROR: the expected value was computed with the same
  mental model used to read the code, so a wrong model agrees with itself.
  Recompute from spec, never from the author's arithmetic.
- INHERITED FRAMING: if the author assumed the code is correct, the tests
  encode that assumption. Do not inherit it. A characterization test
  presented as a correctness check is a defect.

EQUIVALENT-MUTANT BAR
A surviving mutant is NOT equivalent merely because writing a killing test is
tedious. Declare equivalence only with a concrete argument that no observable
behavior distinguishes mutant from original across the whole input domain.
You share the author's laziness gradient — the urge to wave a survivor
through is itself a signal to look harder, not a license to stop.

OUTPUT
Report on two independent axes; never average them.
- FAULT DETECTION: per-finding {location | failure mode | severity
  (block/warn/note) | the execution evidence that would resolve it}.
- ORACLE VALIDITY: per correctness assertion {EXTERNAL / CHARACTERIZED /
  SELF-DERIVED | source if external}.
Verdict: PASS only if no block-severity findings remain AND zero
SELF-DERIVED correctness claims survive. State the predicate you applied.

PROHIBITIONS
- Never propose weakening, deleting, or skipping a test to make a gate pass.
- Never approve to reduce friction, or because the author's reasoning is
  fluent, or because you agree. Agreement triggers re-examination.
- Never let strong fault detection offset unsourced correctness — a sharp
  test asserting the wrong thing is still wrong, and you report it as such.
```

This sharpens the same-family pre-filter as far as a prompt can; it does not make V independent. The residual risk — a blind spot so deep that V shares it even when primed against it — is only covered by X. Keep mutation score and the Q4/Q5 probes as the binding gates; let this V catch everything it can before X has to.

---

## Executor (X) — PR-Time CI Integration

X is where the model-independent verdict becomes binding. The G↔V loop runs *before* the gate (locally or in a pre-merge bot); CI's job is to enforce the predicate that no role can talk its way past. Three X gates, split honestly by how safely they automate:

| Gate | Signal | PR behavior | Why |
|---|---|---|---|
| Mutation on diff | kill rate on changed code | **Blocking** | Deterministic; the binding quality gate |
| Flakiness | nondeterminism over N reruns | **Blocking** (quarantine) | Deterministic; a flaky test has negative value |
| Q4 refactor probe | tests surviving a behavior-preserving transform | **Warn-only → blocking** | Transform can't be *proven* safe in general; promote once FP rate is zero |

### Diff scoping (the trick that makes mutation viable in CI)

Full-repo mutation is intractable per-PR. Scope to changed code and gate on *new* code only — a clean-as-you-code ratchet that never penalizes a PR for pre-existing debt and steadily raises the floor.

```bash
# Compute the changed set against the merge-base (three-dot)
git fetch --no-tags --depth=200 origin "$BASE_REF"
CHANGED=$(git diff --name-only --diff-filter=d "origin/$BASE_REF...HEAD" \
          | grep -E '\.(ts|tsx|js)$' || true)
[ -z "$CHANGED" ] && { echo "No mutable changes"; exit 0; }
```

| Lang | Engine | Diff flag | Incremental cache | Self-enforcing threshold |
|---|---|---|---|---|
| JS/TS | Stryker | `--since=origin/$BASE` | `--incremental` (`reports/stryker-incremental.json`) | `thresholds.break` |
| Java | PIT | `scmMutationCoverage` goal (+ arcmutate git for changed *lines*) | `historyInputLocation`/`historyOutputLocation` | `mutationThreshold` |
| Python | mutmut / cosmic-ray | `--paths-to-mutate "$CHANGED"` (compute yourself) | partial | none — wrapper script enforces |

Granularity caveat: Stryker `--since` and PIT `scmMutationCoverage` mutate whole *changed files*; for changed-*lines* precision (tighter, faster) use arcmutate's git integration on PIT. File-level is a safe over-approximation — start there.

### Runtime control

Mutation cost is O(mutants × test-time); keep it bounded:
- **Test selection** — run only tests whose coverage touches the mutated line (both engines do this from a coverage pass; don't run the whole suite per mutant).
- **Incremental history** — persist the incremental/history file as a CI cache artifact keyed on a coverage hash; unchanged mutants are reused.
- **Per-mutant timeout** + **fail-fast** on the break threshold.
- Budget the job; if diff mutation exceeds it, the diff is too large — a signal to split the PR, not to widen scope.

### Equivalent-mutant escape hatch (with anti-gaming)

Equivalence can't be auto-determined, so survivors that are genuinely equivalent need a suppression — but every suppression must carry a justification and a review trail, or the gate is trivially gamed by suppressing inconvenient survivors.

- Stryker: `// Stryker disable next-line <mutator>: <reason>` — the reason is mandatory by syntax. PIT: arcmutate suppressions / filters with a reason field.
- **CODEOWNERS-protect the gate config and the suppressions path** (`stryker.config.*`, `pitest` threshold, `/.mutation/suppressions/`) so a PR cannot quietly lower its own bar or add an unreviewed suppression. This is the CI analog of no-self-grading: the author of a change can't be the approver of its quality exemption. Route those paths to the V-owner / a human reviewer.

### Q4 refactor probe in CI (the honest one)

A behavior-preserving transform can't be guaranteed in the general case, and a transform that *isn't* actually safe produces false failures that destroy trust in the gate. So tier the transforms by provable safety and promote only when quiet:

1. **Tier 1 — near-zero FP, ship first:** rename local/private identifiers via an AST codemod (ts-morph / jscodeshift for TS; headless IDE refactor for Java). Renaming a private symbol cannot change observable behavior, so any newly-failing test is provably a change-detector.
2. **Tier 2 — nightly, not PR:** reorder demonstrably-independent declarations, extract-method. "Independent" is hard to prove automatically; keep these off the blocking path.
3. **Tier 3 — trivial, low yield:** reformat/whitespace. Catches almost nothing; use only as a smoke check.

```bash
# Tier-1 probe: rename privates, rerun changed-file tests, diff outcomes
cp -r src /tmp/src.orig
node tools/rename-privates.codemod.js $CHANGED      # AST rename, behavior-preserving
npx jest --findRelatedTests $CHANGED --ci > probe.txt || true
git -C /tmp/src.orig ... # restore
# Any test green before and red after == implementation-coupled
diff <(baseline_results) probe.txt
```

Run Tier 1 as a warn-only annotation first. When it produces zero false failures across a representative window of PRs, flip it to blocking. Until then, mutation remains the sole binding quality gate — which is correct, because it's the one that's deterministic.

### Flakiness gate

```bash
# Rerun the changed-file tests under randomized order/seed; quarantine nondeterminism
for i in $(seq 1 "${RERUNS:-20}"); do
  npx jest --findRelatedTests $CHANGED --ci --seed=$RANDOM --shuffle \
    || echo "FAIL run $i" >> flaky.log
done
[ -s flaky.log ] && { echo "Flaky tests detected"; exit 1; }
```

A flaky test is not a slow-to-fix test; it is a gate-eroding liability. Fail the PR, or quarantine to a tracked list with an owner and a deadline — never silently retry-until-green.

### GitHub Actions skeleton (JS/TS, the worked case)

```yaml
name: x-gates
on: [pull_request]
jobs:
  mutation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 200 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm }
      - run: npm ci
      - uses: actions/cache@v4               # reuse incremental results
        with:
          path: reports/stryker-incremental.json
          key: stryker-${{ hashFiles('**/package-lock.json') }}-${{ github.base_ref }}
      - name: Mutation gate (diff-scoped, self-breaking)
        run: npx stryker run --since=origin/${{ github.base_ref }} --incremental
        # stryker.config: thresholds.break = {kill_target}; exits nonzero below it
      - name: Refactor probe (Tier 1, warn-only)
        continue-on-error: true
        run: bash tools/refactor-probe.sh
      - name: Flakiness gate
        run: RERUNS=20 bash tools/flakiness.sh
```

PIT equivalent: `mvn -Pmutation org.pitest:pitest-maven:scmMutationCoverage` with `<mutationThreshold>` set to `{kill_target}` and history locations cached; the goal self-fails below threshold, so no parse script is needed. Python: run `mutmut` over `$CHANGED`, then a wrapper parses `mutmut results` and exits nonzero below threshold.

### Write-back to the orchestrator

X posts results into the per-module state manifest and onto the PR: mutation score (with the previous score, to show the ratchet direction), the survivor list as inline annotations on the offending lines, and the flakiness/probe outcomes. Surviving non-equivalent mutants become the exact remediation tasks the G↔V loop consumes on the next iteration — so the CI gate and the agent loop share one artifact, and a red gate hands G a precise worklist rather than a percentage.

This closes the loop: the deterministic gate runs on every PR, scoped to the diff, ratcheting new code upward, with the one un-automatable check held warn-only and honestly labeled as such. Mutation score is binding because it cannot be reasoned past; everything advisory stays advisory.

---

## Oracle-Mining Pipeline

The whole correctness axis rests on finding expected behavior from a source *independent of the code under test*. A legacy untested repo rarely has a spec, but it is not oracle-free — intent is latent in history, types, contracts, and people's heads. This pipeline discovers that intent, grades it, and converts it into citable assertions, while structurally refusing the circular trap (using the code's own output as the standard for the code's correctness). It uses existing roles: **X** harvests deterministically, **G** extracts and normalizes, **V** owns the independence gate, **H** supplies intent only where nothing else can.

### Grade every candidate on two axes

A real oracle needs both:

- **Independence** — how decoupled is this source from the implementation? Could it *disagree* with the code? Anything derived by reading the code has zero independence, however authoritative it looks.
- **Authority** — does it speak to *intended* behavior, or merely *observed/incidental* behavior?

The dangerous quadrant is high-authority / low-independence: a golden file captured from running the code looks like ground truth but is pure characterization. The cheap-but-shallow quadrant is high-independence / low-authority: a type signature constrains shape but not semantics.

### Source taxonomy (graded)

| Source | Independence | Authority | How to extract / notes |
|---|---|---|---|
| External standard / protocol (RFC, ISO, payment spec) | High | High | Often ships **test vectors** — pure oracles. Detect by imports, format names, conformance comments |
| Human SME (elicited) | High | High | Gold fallback; expensive — spend it last and narrowly |
| Regulatory / domain rules (tax, retention) | High | High | Authoritative for the domain; may exist as written policy |
| **Closed bug reports + fix commits** | High | High | Underused. Report = "should X, does Y"; fix pins input→output. Each is a regression oracle |
| Acceptance criteria in tickets / stories | High | Med-High | Use only the parts describing behavior, not implementation |
| Downstream consumer expectations | High | Medium | What callers rely on = de facto contract; mine from fan-in (seam map). Formalize as consumer-driven contracts |
| Reference / legacy twin implementation | High | High | **Differential oracle** — if a system is being replaced, the old one is a free, fully-independent oracle |
| Schemas / IDL (OpenAPI, protobuf, JSON Schema, DB constraints) | Med-High | Medium | Constrains shape/range/nullability, rarely full semantics. Lower if generated *from* code |
| Type signatures | Medium | Low-Med | Cheap shape/nullability oracle; weak on semantics |
| In-code guards / `require` / validators / thrown errors | Medium | Medium | Encode authors' *intended* pre/postconditions — closer to intent than surrounding logic. Check they aren't vacuous |
| Domain-derived properties (round-trip, idempotence…) | High | High | **Metamorphic oracles** — see below. Highest leverage |
| Existing repo tests | **Varies** | Varies | Classify, never assume: spec-authored = real; code-read or characterization = pseudo |
| Golden files / captured output | **None** | High-looking | **Pseudo-oracle.** Characterization only — never a correctness oracle |
| Comments restating code; LLM inference from the impl | **None** | None | Banned. This is exactly the `SELF-DERIVED` trap Q3 catches |

### Metamorphic & property oracles — the cheat code

These require no known output — only a relationship that must hold — so they sidestep the oracle problem entirely and need zero human time. The miner pattern-matches the seam map's roles to propose them automatically:

| Pattern | Detect by | Oracle form |
|---|---|---|
| Round-trip | parse/serialize, encode/decode, to/from pairs | `decode(encode(x)) == x` |
| Inverse | a function and its stated inverse | `f⁻¹(f(x)) == x` |
| Idempotence | normalizers, dedupe, saves, setters | `f(f(x)) == f(x)` |
| Commutative / associative | merge, union, arithmetic | `f(a,b) == f(b,a)` |
| Order / monotonicity | sorts, rankers, time series | ordering preserved under op |
| Conservation / invariant | accounting, inventory, transforms | total/sum preserved |
| Differential | reference lib or legacy twin exists | `out == ref(in)` |

Always exploit an available property oracle regardless of risk tier — it's cheap, strong, and fully independent.

### Pipeline stages

**0 · Harvest (X + G).** Per unit, enumerate candidate sources: VCS history and `blame` with linked issues/PRs, docstrings, types, schema/IDL files, in-code asserts, referenced standards, consumer call sites (from seam-map fan-in), existing tests, `/docs`. Deterministic gather; G assembles the candidate set.

**1 · Independence gate (V).** Grade each candidate on both axes; discard or demote pseudo-oracles with a reason. This is V's job specifically because it is the same skepticism the hardened verifier prompt encodes — golden output, code-derived comments, and impl-inferred values are rejected here, not later.

**2 · Extract & normalize (G).** Convert each surviving source into a structured **claim** (schema below). A bug report becomes an example claim + the regression it guards; a parser/serializer pair becomes a property claim; an OpenAPI schema becomes a postcondition; a `require` becomes a precondition plus its error contract.

**3 · Corroborate & resolve conflicts (G → V/H).** Multiple sources on one behavior: agreement raises confidence; disagreement is *signal, not noise* — a type says non-null while a consumer handles null, or a docstring contradicts a bug-fix, usually means a latent bug or a stale doc. Promote corroborated claims; escalate unresolved conflicts to H. This stage produces value beyond tests: it surfaces the codebase's contradictions.

**4 · Assess coverage & route gaps (X + G).** Per unit, does the claim set cover happy path, boundaries, and error conditions with sufficient authority? Combine with the risk score and route:

| | Strong oracle coverage | Weak / none |
|---|---|---|
| **High risk** | → Phase 4 with mined oracles | → **Human elicitation** (spend H budget here) |
| **Low risk** | → Phase 4 with mined oracles | → **Characterization-only**, explicitly labelled |

Property oracle available → exploit it in any cell, no human needed.

**5 · Elicit as review, not authoring (G → H).** For routed units, never ask H "what should this do?" open-ended. Present the weak/conflicted claims and concrete proposed assertions to confirm / deny / correct — review is far cheaper than authoring. Batch by subsystem so H stays in one context. Each answer becomes a high-authority claim reusable by every test touching that behavior, so the human cost amortizes across the suite.

**6 · Oracle ledger.** A persistent, provenance-tracked store of all claims that Phase 4 cites and Q3 audits against. Its byproduct is the specification the codebase never had — accreted incrementally, re-runnable, and growable as new bugs and consumers appear.

### Claim schema

```yaml
claim:
  id: oc-payments-ledger-0007
  unit: payments/ledger.applyRebate
  kind: postcondition          # precondition|postcondition|invariant|example|property|error
  statement: "rebate never exceeds order subtotal"
  oracle:
    source: "issue#1423 + fix a1b2c3"
    independence: high          # high|medium|low — could it disagree with the code?
    authority: high             # high|medium|low — does it speak to intent?
  corroborated_by: ["type:Money(non-negative)", "consumer:CheckoutSvc"]
  status: confirmed             # mined|conflicted|elicited|confirmed|unspecified
  cited_by: ["tests/unit/ledger_rebate_test#caps_at_subtotal"]
```

A Phase 4 assertion is valid only if it cites a claim whose `independence` is not `low` — which makes Q3's provenance audit a lookup, not a judgment call.

### Key prompts

**Extraction (G, after X harvests):**
```
For {unit}, you are given harvested candidate sources (history, types,
schemas, in-code asserts, consumer call sites, referenced standards).
Emit normalized claims per the schema. For each:
- classify kind; write the behavioral statement in spec terms, NOT by
  paraphrasing the implementation;
- grade independence and authority honestly;
- detect property-oracle patterns (round-trip, idempotence, inverse,
  conservation, differential) from the unit's role and emit them — these
  need no known output.
Mark any source you cannot tie to intent as UNSPECIFIED. Do not invent a
claim to fill a gap.
```

**Independence gate (V):**
```
Re-grade each claim's independence adversarially. REJECT any whose
expected behavior could only have been known by reading the code under
test — golden output, code-restating comments, impl-inferred values,
characterization tests. A claim that merely looks authoritative is not
independent. Output: kept claims, rejected claims with reason, and any
HIGH-authority/LOW-independence items flagged as characterization, not
correctness.
```

**Elicitation packet (G → H):**
```
For the units routed to elicitation, produce a batched review packet
grouped by subsystem. For each, present: the weak/conflicted mined claims,
the specific ambiguity, and 2–4 concrete proposed assertions phrased as
yes/no/correct-it. Lead with the highest-risk units. Keep each decision
answerable in under a minute without reading source. Capture answers as
ELICITED, HIGH-authority claims.
```

### Honest limits

Mining cannot manufacture intent that was never recorded anywhere. For genuinely undocumented business logic with no consumer constraint and no SME memory, there is no oracle — the correct move is to characterize it, label it `unspecified`, and surface it as organizational risk (behavior whose intent now exists nowhere). Do not let any role fabricate intent to close the gap; a confidently invented oracle is worse than an admitted absence, because it certifies a guess as a requirement.

### Harvesting layer (Stage 0 extractors)

The harvesters are deterministic (X): they **gather and locate**, they never judge independence or write claims — that separation is what keeps the pipeline honest. Each extractor emits raw *candidates* with exact, re-fetchable provenance; G extracts claims from them and V grades them downstream. Most of this is a second pass over the Phase 0 analysis substrate (AST, call graph, unit line-spans), not new infrastructure.

**Unit anchoring — the precision crux.** Every artifact below lives at file/line/commit granularity, but oracles attach to *units*. Build a unit-line index from the seam-map AST, then every candidate carries the unit id(s) whose line span its locator intersects. Without this join, you get file-level noise instead of unit-level oracles. The anchoring index is therefore the first extractor; all others join against it.

| Extractor | Pulls from | Technique | Emits | Default I / A |
|---|---|---|---|---|
| **Unit index** (prereq) | seam-map AST | symbol → {file, line-span, stable id} | the join key | — |
| VCS history | git log / blame | commits touching the unit's span; `blame` → last-author (SME routing) | change context, author | — |
| **Bug-fix / revert** | git + issue tracker API | see algorithm below | regression examples, negative oracles | high / high |
| Schema / IDL | OpenAPI, protobuf, GraphQL SDL, JSON Schema | parse → field types, required, enum, min/max, format, error responses | shape/range postconditions | med-high / medium |
| DB constraints | migrations / DDL | parse NOT NULL, CHECK, UNIQUE, FK | data invariants (a `CHECK(balance>=0)` is a real postcondition) | high / medium |
| Call-site / consumer | seam-map fan-in | per caller: fields accessed, non-null assumptions, range branches, catch blocks, caller asserts | de facto contracts | high / medium |
| In-code contracts | AST scan | guards, `require`/`assert`, `requireNonNull`, validation annotations (`@NotNull`,`@Min`; Zod/Joi), throw-sites + their conditions | pre/postconditions, error contracts | medium / medium |
| Docstrings | AST doc-comments | structured tags (`@throws…when`, `@param`, `@returns`) > prose | candidate behavior (independence suspect — may be code-derived/stale) | low-med / medium |
| Standards / vectors | imports, RFC/ISO refs in comments, format-bearing roles | identify implemented standard; **locate its published test vectors** | conformance examples (pure oracles) | high / high |
| Reference impl | sibling/vendored/legacy module or equivalent lib | detect functional twin | differential oracle target | high / high |
| Existing tests | test files touching the unit | collect + provenance hints (ticket refs? committed with feature vs. with "add characterization") | candidate oracles to be classified | varies |

**Bug-fix extractor (the highest-value, least-obvious one):**
```
for each commit C where message ~ /fix|bug|regression|hotfix/i
                       OR C links an issue labelled bug/defect:
  hunks   = diff(C); units = anchor(hunks)        # line-span intersection
  issue   = tracker.fetch(linked_ref(C))          # body: "expected X, actual Y"
  addedT  = tests added/modified in C             # author's own regression assertions
  emit candidate{
    unit: units, source_type: bug_fix,
    locator: "issue#<n> + <sha>",                 # exact, re-fetchable
    raw: issue.body, signal: {input: repro, expected: issue.expected},
    suggested_kind: example, I: high, A: high }
for each revert R:
  emit candidate{ source_type: revert, ... }      # negative oracle: this behaviour was wrong
```
A bug report is high-independence precisely because the reporter described desired behavior *without* reference to the broken implementation — that is why this source outranks almost everything else, and it is sitting unused in your history.

**Candidate schema (pre-extraction raw material):**
```yaml
candidate:
  unit: payments/ledger.applyRebate
  source_type: bug_fix
  locator: "github:issue/1423 + commit/a1b2c3d"     # exact + re-fetchable → Q3-auditable
  raw: "rebate of $12 on a $10 order produced -$2 total; expected rebate capped at subtotal"
  signal: { input: "rebate=12, subtotal=10", expected: "total>=0 && rebate<=subtotal" }
  suggested_kind: example
  suggested_independence: high      # heuristic default from source_type; V may override
  suggested_authority: high
  harvested_at: <repo-commit-sha>   # determinism key
```

**Operational properties.**
- *Determinism & caching* — harvesting is a pure function of repo state plus external refs; cache keyed on `harvested_at`. On a PR, re-harvest only changed units.
- *Provenance precision* — every candidate carries an exact locator (sha / file:line / issue URL / schema path). This is non-negotiable: it's what makes the ledger verifiable and Q3 a lookup rather than a judgment.
- *Boundary* — X never sets a *final* grade or writes a claim. `suggested_*` fields are source-type defaults; the independence gate (V) owns the real grading. Keeping X precise-but-dumb preserves no-self-grading.

**Integration requirements this introduces.**
- Static-analysis substrate per language: TS → ts-morph / TS compiler API; Java → JavaParser or Spoon; or tree-sitter for a language-agnostic AST + line-span index (reuses Phase 0).
- Issue-tracker / VCS-platform API access (GitHub/GitLab/Jira) with tokens, to resolve commit↔issue links and fetch bodies/labels — rate-limited, so cache aggressively.
- Format parsers: OpenAPI/Swagger, protobuf, GraphQL SDL, JSON Schema, and a SQL-DDL/migration reader.
- For standards: a small curated map of standard → published test-vector location, since vectors are the cheapest pure oracles available and worth fetching once.

The output of this layer is a per-unit candidate bundle that drops directly into the Stage 2 extraction prompt — at which point the pipeline already described takes over.

---

## Orchestrator Runtime

The spec so far is declarative; this is the layer that executes it and survives failure. Runs span days across many modules, so the binding requirement is **durable execution**: a crash resumes from where it stopped, never restarts. Everything below follows from that.

### The determinism boundary (the linchpin)

Durable engines replay workflow code to rebuild state after a crash, so workflow logic must be deterministic. But our work is saturated with non-determinism — LLM calls, mutation runs, git state, time, the human. The discipline that resolves this is also exactly the discipline our role split already imposes:

> All non-determinism lives in **activities** whose outputs are journaled. The **workflow** is pure phase-sequencing logic. On replay the engine feeds back recorded activity results; it never re-invokes them.

So G/V calls, every X tool run, and H inputs are activities (recorded, retryable, idempotent); the phase state machine is the deterministic workflow. LLM calls being activities is not optional — a replay must not re-prompt the model and get a different answer.

### Two layers

- **Module Workflow** — one durable instance per module, progressing through the P0→P6 state machine. Its state *is* the per-module manifest. Independent, resumable, isolated.
- **Campaign Orchestrator** — manages the fleet: wave ordering (Wave 1 reaches a passing P6 before Wave 3 starts), concurrency caps, global budget + kill switch, backpressure on the mutation-compute bottleneck.

### Event-sourced state

The manifest is a *projection* of an append-only event log (`PhaseEntered`, `GatePassed`, `GateFailed`, `MutationScored`, `Escalated`, `HumanAnswered`, …). This buys four things at once: crash recovery, a complete audit trail of what the agent changed and why (your DevSecOps requirement), time-travel debugging, and deterministic replay. The YAML manifest is just the current-state view.

### Human gates are durable waits, not polling

H touchpoints can't block a thread for days. The workflow parks on a durable signal (`await human_signal("oracle_review")`) consuming zero compute, and resumes the instant the answer event arrives — a week later if need be. This is the single biggest reason the durable model fits: seam sign-off, oracle elicitation, and every escalation are durable parks, and the human queue is just the set of outstanding waits.

### Failure taxonomy — keep these separate or you corrupt the loop

The common mistake is letting a generic retry policy re-run a *semantic* gate. Mutation-below-target is not a fault to retry; it's a loop iteration.

| Class | Example | Handling | Owner |
|---|---|---|---|
| Transient infra | API 429, network blip | retry w/ backoff + jitter | engine |
| Output drift | model returns wrong shape | bounded validate-and-retry; record | workflow |
| Semantic gate fail | mutation < target | **not a retry** — route through the state machine (loop / escalate) | workflow logic |
| Hard invariant breach | net red, unsourceable assertion | halt + escalate; park | H |
| Non-convergence | MAX_ITERS hit | circuit-break module → `BLOCKED`; fleet continues | campaign |

### Mechanical invariant enforcement (cashing the earlier promise)

The runtime enforces in code what the prompts only request — these are guard activities the workflow must pass, not advisory text:

- **Net immutability** — a guard checksums the frozen net before and after any P4 edit; the net files are mounted read-only in G's workspace. Mismatch → halt.
- **Oracle provenance** — the P4 commit activity rejects any assertion not citing a ledger claim with `independence ≠ low`. Q3 becomes a precondition, not a review.
- **No-self-grading** — V and X activities are routed by config to a *different* endpoint than G; the workflow physically cannot call G to grade its own output.
- **Protected gate config** — thresholds and suppressions are read from a CODEOWNERS-locked ref, never from the PR branch, so a run can't lower its own bar.

### Module workflow (durable, engine-agnostic sketch)

```
workflow ModulePipeline(module):
  state = replay_or_init(module)                       # event-sourced

  seam = act.G_seam_map(module)
  require act.V_seam_gate(seam)                         # V endpoint ≠ G
  await human_signal("seam_signoff", module)           # durable park

  risk  = act.X_rank(module)                            # git-derived, deterministic
  cands = act.X_harvest(module)                         # cached on repo sha
  claims = act.V_independence_gate(act.G_extract(cands))
  if weak(claims) and high_risk(risk):
      await human_signal("elicit", module)              # → ELICITED claims

  net = act.G_characterize(module)
  require act.X_net_green(net, source="unmodified")
  act.freeze_net(net)                                   # checksum + chmod ro

  with workspace_checkpoint(module):                    # restorable on resume
      act.G_refactor_and_unit(module, claims)
      require act.X_net_still_green()                    # else HALT: behaviour changed
      require act.guard_oracle_provenance()             # every assertion cites indep≥med
      await human_signal("oracle_review", module)       # Q3

  act.G_contract_tests(module)

  for i in 1..MAX_ITERS:                                 # durable loop
      report = act.X_mutation_diff(module)               # checkpoint workspace each iter
      emit MutationScored(report)
      if report.score >= target:               return DONE
      if act.V_all_equivalent(report.survivors): return DONE(documented)
      act.G_write_kills(act.V_triage(report.survivors))
  escalate("mutation_non_convergence", report);          return BLOCKED
```

Every `act.*` is journaled and idempotent; every `require` failure routes through the state machine, not a blind retry; every `await` is a zero-compute durable park.

### Workspace lifecycle & recovery

Each module owns an isolated working copy (git worktree or ephemeral container) recorded by `{branch_ref, base_sha}` in state. On resume the engine replays the event history to rebuild in-memory state without re-running recorded activities, re-hydrates the workspace from the recorded refs, re-arms pending human waits, and re-runs only any in-flight activity that never journaled its result — which idempotency makes safe. Mutation runs execute on pooled ephemeral runners under a semaphore, since that's the compute bottleneck.

### Engine options (honest)

- **Temporal-class** (Temporal, Restate) — mature durable execution, first-class signals for the human waits, a clean determinism model, self-host or managed. Best fit for our human-wait + tight-loop + retry profile. Recommended.
- **AWS Step Functions** — managed and durable, but long human waits, the P6 iteration loop, and large state are clumsy to express; serviceable, not comfortable.
- **Inngest / event-driven** — simpler to adopt; you'll hand-roll more of the loop and budget logic.
- **Build-your-own** (event log + queue + checkpointing) — maximum control, but you are reimplementing durable execution; choose only if a hard constraint forbids the above.

### How it wraps your existing harness

Your Claude-Code orchestration becomes the **activity implementation** for G and V — the runtime invokes a harness session as a recorded activity rather than calling it directly. X tools (mutation, git, harvesters, parsers) are activities too. The orchestrator is the new layer on top; the harness keeps doing what it already does, now under durable, audited, crash-safe control with the invariants enforced around it.

---

## Build &amp; Pilot Sequence

Everything above is architecture. This is the order to build it and the experiment that tells you whether it works before you commit. Two principles govern the sequence:

1. **Vertical slice before horizontal scale.** Build a minimal version of *every* component, wired end to end on one module, before building any component broadly. A walking skeleton surfaces design-meets-reality failures while they're cheap.
2. **Build the orchestrator last.** The durable runtime earns its keep at fleet scale, not on one module — a human can re-run a single pilot by hand. Starting on the runtime is building crash-recovery for a flight you haven't flown.

### Foundations (before any phase runs)

- **F1 · Test environment.** The pilot module's tests must *execute deterministically* — DB, fixtures, doubles, containers. For an untested legacy repo this is often the hardest and most underestimated prerequisite; until it exists, X has nothing to gate on. Do this first.
- **F2 · Static-analysis substrate.** AST + call graph + unit-line index for the module's language (ts-morph / JavaParser / tree-sitter). The seam map and every harvester join against it.
- **F3 · Endpoints.** Wire G and V to *separate* endpoints (different context at minimum, different vendor if you can), load the hardened verifier prompt into V.

### Phase A — Walking skeleton (one module, driven by hand or a script)

Minimal version of each component, run manually so you can watch every gate fire. Record everything — this run is your calibration dataset.

| Step | Build | Proves |
|---|---|---|
| S1 | Seam map + your sign-off | anchoring and the seam gate work on real code |
| S2 | Harness + smoke; mutation engine runs on the module | the binding gate's machinery functions |
| S3 | Oracle for *this module only*: run the bug-fix extractor over its history, detect any property oracle, hand-curate the rest into a ledger | **whether real oracles exist for real code** |
| S4 | Characterization net, frozen | the safety net and immutability guard hold |
| S5 | Refactor + unit tests; provenance guard; your Q3 review | sourced assertions are achievable, not just aspirational |
| S6 | Mutation loop: X scores → V triages → G kills, to target or escalate | the adversarial loop converges |
| S7 | Two-axis scorecard (Q6) | the quality measure is meaningful |

Do **not** stand up the durable orchestrator for this. A shell script calling the activities in order is the right tool.

### Pilot module selection

The module must exercise every gate yet finish. Choose one that is:

- **High-risk but medium seam-cost** — real stakes and real refactoring, but tractable. Save the worst-entangled module for the *second* run; a pilot that never finishes teaches nothing.
- **Logic-bearing, not I/O glue** — mutation testing and oracles have teeth on logic; a thin wrapper proves little.
- **Equipped with real oracle sources** — deliberately pick one *with* bug history and a consumer or schema, so the correctness path is exercised, not just characterization. A module with zero recoverable intent can't test the riskiest subsystem.
- **Property-oracle-shaped if possible** — a calculator, parser, serializer, or validator — to validate the highest-leverage oracle path.

Concretely: a pricing/eligibility/rebate calculator, a parser, or a state machine with a few closed bugs in its history is close to ideal.

### Acceptance criteria — the pilot is an experiment, design it to falsify

The two assumptions most likely to sink the whole plan are that **minable oracles exist in sufficient density**, and that **a same-family V adds enough independent signal**. The pilot exists to test those cheaply, ahead of any scaled spend. Treat each criterion as a falsifiable hypothesis:

**Do the gates bite?**
- *Seeded-fault test* — after the suite is built, inject several deliberate bugs; the suite must go red on each. A surviving fault means the gate doesn't bite — a design problem, not a tuning one.
- *V independence (the risky one)* — measure how many real findings V raised on G's tests. Near zero means V isn't adding independent signal → escalate to a cross-vendor V before scaling.

**Does oracle mining actually yield?**
- *Oracle yield (the other risky one)* — what fraction of correctness assertions cite an independent (`≠ low`) oracle vs. fall back to characterization or elicitation? Near-zero mined yield means you're elicitation-bound, which sets your real throughput ceiling and human-time budget. This is the single most important number the pilot produces.
- *Circularity spot-check* — manually audit a sample of `EXTERNAL` assertions; did anything code-derived slip past V?
- *Conflict value* — did corroboration surface any genuine bug or stale doc? (Evidence the independence axis is doing work.)

**Is it viable at scale?**
- *Cost* — total tokens + compute for one module, extrapolated to N modules. Go/no-go.
- *Human time* — how long your two touchpoints actually took; extrapolated, is elicitation the bottleneck?
- *Convergence* — loop iterations to target; routinely hitting MAX_ITERS means the loop isn't converging.

**Do the false-positive gates behave?**
- *Refactor probe FP rate* — zero false failures from the Tier-1 rename probe is the bar to promote it from warn-only to blocking.
- *Suite determinism* — did the new suite come out flake-free under the rerun gate?

### Phase B — Harden &amp; broaden (only after the slice proves out)

In dependency order, calibration first:

1. **Calibrate constants** from the pilot data: `kill_target` (what's achievable), risk weights (against the module's real defect history), `MAX_ITERS`, refactor-probe FP rate. Stop using placeholders.
2. **CI/X integration** — wire the proven mutation + flakiness gates into PR CI, diff-scoped with the new-code ratchet; refactor probe warn-only.
3. **Full harvester suite** — build the remaining extractors, *prioritized by which sources actually yielded oracles in the pilot*. You may find some sources are dry for your codebase and rightly deprioritize them.
4. **Durable orchestrator** — now build the runtime, wrapping the now-stable activities, with the real failure modes you observed made durable.
5. **Human review surface** — sized to the real review volume the pilot revealed.
6. **Observability** — the dashboard projection over the event log.
7. **Scale to waves** under the orchestrator with budget caps and the kill switch.

### Critical path

`F1 test environment → F2 substrate → S1–S7 slice → calibrate → orchestrator → scale.` The test environment and the oracle-yield result are the two places the plan is most likely to stall or change shape, so front-load both: F1 first, and design the pilot specifically to measure oracle yield early. Everything else is comparatively predictable engineering.

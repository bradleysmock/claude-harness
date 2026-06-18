# test-harness

A Claude Code plugin for retrofitting a **high-integrity test suite** onto an untested codebase. It encodes a seam-aware, risk-ranked, oracle-grounded, mutation-gated workflow, and enforces its two most important invariants — net immutability and oracle independence — mechanically rather than by prompt.

Full rationale: [`docs/DESIGN.md`](docs/DESIGN.md).

## Why it's built this way

Three ideas drive the design:

- **Generator / Verifier separation.** The model that writes a test is the worst judge of it — the blind spot that produced a weak test reproduces in the self-critique. So tests are written by the `generator` agent and gated by a separate `verifier` agent that **cannot edit code** (`disallowedTools: Write, Edit`). That's no-self-grading enforced at the tool layer, not requested in a prompt.
- **The oracle problem is the real problem.** Correctness assertions must come from a source independent of the code under test. The oracle commands mine that independence from git/bug history, schemas, consumers, and standards, and a Phase 4 assertion is only valid if it cites an oracle whose `independence ≠ low`.
- **Mutation score, not coverage, is the binding gate.** Coverage proves a line ran; mutation testing proves a fault in it would be caught.

## Install

Local dev, from the repo containing this folder:

```bash
claude --plugin-dir ./test-harness
# then /reload-plugins after edits
```

Or install across machines via the marketplace. Place `marketplace.json` at the **repo root** in `.claude-plugin/marketplace.json` (not in this plugin folder); `owner` and `plugins` are required, and `./test-harness` resolves relative to the repo root:

```json
{
  "name": "claude-harness",
  "owner": { "name": "Bradley" },
  "plugins": [
    { "name": "test-harness", "source": "./test-harness", "version": "0.1.0" }
  ]
}
```

Then, from a local clone (relative `source` only resolves when the marketplace is added via Git or a local path):

```bash
/plugin marketplace add ./                      # or:  <owner>/claude-harness  once pushed to GitHub
/plugin install test-harness@claude-harness
claude plugin validate ./.claude-plugin/marketplace.json   # optional schema check
```

## Workflow (commands are namespaced `/test-harness:`)

Run a single module end-to-end with `/test-harness:run-module <path>`, or step through:

| Command | Phase | Gate owner |
|---|---|---|
| `seam-map` | P0 · classify deps, seam types, refactor cost | V → human |
| `infra` | P1 · harness + smoke + mutation engine | X |
| `risk-rank` | P2 · churn × blast-radius × defects → waves | V |
| `harvest` → `oracle-extract` → `elicit` | Oracle mining | V + human |
| `characterize` | P3 · records behavior; **freezes the net** | X |
| `unit-tests` | P4 · refactor + sourced assertions | X · V · human |
| `contract-tests` | P5 · lock seams | V |
| `mutation-gate` | P6 · binding adversarial loop | X · V |
| `quality-audit` | Q1–Q6 two-axis scorecard | V |

## Agents

- **`generator`** (sonnet) — writes analysis and tests under oracle-sourcing discipline.
- **`verifier`** (opus, high effort, worktree isolation, no write tools) — the hardened adversarial critic. To get true independence, point it at a different vendor in your harness config; same-family is a pre-filter, not a guarantee (see `docs/DESIGN.md` → model matrix).

## Mechanical enforcement (the hook)

`hooks/hooks.json` registers a `PreToolUse` guard (`scripts/net-guard.sh`) that **blocks any edit to a frozen characterization-net file**. `scripts/freeze-net.sh` records the net's files + checksums into `.test-harness/frozen-net.txt`; after that, the generator physically cannot edit the net to make a test pass — it must escalate.

## X-side scripts (deterministic)

| Script | Role |
|---|---|
| `net-guard.sh` | the PreToolUse net-immutability hook |
| `freeze-net.sh` | freeze a characterization net |
| `mutation-diff.sh` | diff-scoped mutation run (Stryker / PIT / mutmut), new-code ratchet |
| `harvest-bugfix.sh` | mine bug-fix + revert commits as high-independence oracles |
| `refactor-probe.sh` | Q4 Tier-1 behavior-preserving probe (warn-only) |

Runtime artifacts (ledger, manifests, scorecards) land in `.test-harness/`.

## Calibration

`kill_target` (0.75), `MAX_ITERS` (4), and the risk weights are placeholders. Run the one-module pilot (`run-module`), capture oracle yield and verifier catch-rate, and set them from data before scaling. See `docs/DESIGN.md` → Build & Pilot Sequence.

## Per-stack work you supply

The static-analysis substrate, the Tier-1 rename codemod (`RENAME_CODEMOD`), engine config (`stryker.config` `thresholds.break` / PIT `<mutationThreshold>`), and issue-tracker tokens for oracle harvesting are stack-specific. The scripts are the harness around them.

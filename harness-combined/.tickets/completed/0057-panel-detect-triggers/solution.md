# Solution

**Ticket**: 0057
**Title**: Panel-detect script: deterministic trigger table in context/panels/triggers.md

## Approach

Move panel activation across the LLM/Python boundary (0053). The 30-row prose
table in `skills/critique/SKILL.md` is normalized into typed TOML inside
`context/panels/triggers.md`; a stdlib-only `panel_detect.py` evaluates it
deterministically over (root, in-scope files) and emits JSON. Judgment-only
triggers stay prose and surface as candidates the model must disposition.
Review-behavior prose (deference, deferred-panels, design-mode inference) stays
in the skill; all six consumers plus panel boilerplate repoint.

## Components

| Component | Responsibility |
|-----------|----------------|
| `context/panels/triggers.md` | Preamble (incl. explicit note that manifest-presence rows now activate deterministically — e.g. Python on a docs-only review in a Python repo — a chosen behavior change) + one fenced TOML block: `[panels.<key>]` with `file`, `globs`, `manifests`, `deps`, `path_keywords`, `content`, `judgment`; provenance comments on prose→judgment downgrades; core always-active; secondary.md excluded by design (0048's existing exclusion). |
| `panel_detect.py` | CLI `--root DIR [--design] [--triggers PATH] FILE...`. Containment-verifies each FILE under root. Matches globs (posix relpaths), manifest presence, deps (structured parse: json/tomllib; word-boundary regex elsewhere; root + in-scope manifests), path keywords, content regexes (size-capped). JSON out: `active` (core first, table order; evidence = kind + path + pattern id, never content), `candidates` (judgment reasons; in `--design`, unevaluable dep/content panels too), `skipped` (reason-tagged). Exit 2 + stderr on missing/unparseable/schema-invalid triggers or ≠1 TOML fence. |
| Consumer edits | SKILL.md Step 1: table deleted; run-script instruction; per-candidate activate/defer disposition line mandated; design-mode = model infers scope, runs with `--design`, judges candidates. Non-empty `skipped` must be surfaced in the report header. Repoint critic-brief.md (incl. stale "29 panels" prose), review SKILL.md, build-ticket.md, README.md (line ~216), all panel boilerplate lines. |
| `tests/test_0048_panel_consistency.py` | Rewritten: parses triggers.md TOML instead of the SKILL.md table; keeps bijection + no-inline-pattern assertions; panel headers must cite triggers.md. |
| `tests/test_0057_panel_detect.py`, `tests/test_0057_triggers_parity.py` | Unit + integration per Test Plan. |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| TOML block in markdown | Stdlib `tomllib` (precedent `gates/__init__.py`); file stays human-curated docs. |
| Typed fields + prose `judgment` | Encodes exactly what is deterministic; never fakes determinism (0053). |
| Structured manifest parse over substring scan | Substring is deterministically *wrong* (`preact`→React); word-boundary fallback only where stdlib can't parse. |
| `--design` emits unevaluable panels as candidates | Closes the silent-drop gap for Identity/Crypto/AI-LLM in design reviews — in Python, not model memory. |
| Evidence excludes file content | Repo under review is untrusted input; no injection path into the critic's context. |
| Exit 2 fail-closed incl. schema | A typo'd field silently disabling a trigger recreates the divergence class this ticket eliminates. |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Shipped triggers.md parses; entry set == panels dir minus core/secondary (30 today, derived not hardcoded); files exist. |
| FR-2 | Unit | Fixtures per kind: glob, manifest presence, dep, path keyword, content regex. |
| FR-3 | Unit | `preact`/`react-scripts` no-match; pyproject dep parse; go.mod word-boundary; nested manifest consulted. |
| FR-4 | Unit | Judgment-only panel never `active` from prose; provenance comments present on downgraded rows. |
| FR-5, FR-9 | Unit | JSON contract; core-first order; byte-identical repeat run. |
| FR-6 | Unit | Evidence fields only kind/path/pattern-id; fixture match-line contains instruction-like text that must not appear in output. |
| FR-7 | Unit+Int | Candidates carry reasons; `--design`: root `package.json` dep still activates deterministically, content-dependent panels emit as candidates. |
| FR-8 | Unit | Missing/corrupt TOML, unknown key, wrong type, missing `file`, 0/2 fences, nonexistent `--root`, empty file list sans `--design` → exit ≠ 0, stderr, no JSON. |
| FR-10 | Unit | Content checks: SKILL.md table gone + script + disposition instruction; brief/review/build-flow/README/panel boilerplate cite triggers.md. |
| FR-11 | Unit | Rewritten 0048 green against triggers.md; parity both directions; every content regex compiles + backtracking-shape lint. |
| NFR-1 | Unit | One case per skip reason: oversize, missing, unreadable, binary, out-of-root. |
| Integration | Integration | Worked examples: `app/routes/users.py` → Core+Python+HTTP/API; TSX → Core+TS+UI; `migrations/001.sql` → Core+Database. |

## Tradeoffs

- **Candidates-not-activation for judgment rows because**: encoding them as
  patterns silently narrows coverage; the model keeps that call — but must
  disposition each candidate visibly (activate/defer + reason).
- **In-scope-files input over repo scan because**: activation is per-review
  scope; callers already own the file list.
- **Accepting risk of**: extraction infidelity — mitigated by per-kind tests,
  provenance comments, bijection (0048) both ways, worked-example integration.

## Risks

- `skills/critique/SKILL.md` + README are shared-conflict hotspots — soft-squash
  + rebase-before-deliver recipe.
- Manifest-presence over-activation is a real behavior change — documented in
  the triggers.md preamble (see Components) so it reads as chosen.

## Implementation Order

1. Write test files (red): detect unit/integration, parity, consumer content
   checks, and the 0048 rewrite (against the not-yet-existing triggers.md).
2. Author `context/panels/triggers.md` (normalize 30 rows; provenance comments).
3. Implement `panel_detect.py` to green detect + parity + 0048 tests.
4. Repoint consumers (SKILL.md Step 1 rewrite, brief, review, build flow,
   README, panel boilerplate); green content checks.
5. Gate-exact ruff + mypy on new/changed Python; full targeted pytest.

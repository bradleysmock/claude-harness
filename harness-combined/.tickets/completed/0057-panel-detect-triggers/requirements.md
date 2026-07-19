# Requirements

**Ticket**: 0057
**Title**: Panel-detect script: deterministic trigger table in context/panels/triggers.md

## Functional Requirements

1. `context/panels/triggers.md` must hold canonical trigger data in exactly one
   fenced TOML block: an entry per panel file in `context/panels/` except `core.md`/`secondary.md` (30 today — tests must derive the set from the directory, never hardcode a count),
   each naming its panel file; core always-active; secondary excluded by design (0048's exclusion).
2. Each entry must encode deterministic triggers as typed fields: file globs,
   manifest presence, dependency names, path keywords, content regexes (matched against file text, including string literals).
3. Dependency matching must parse structured manifests via stdlib (JSON, TOML),
   use word-boundary line regexes elsewhere (requirements.txt, go.mod, Gemfile), and consult root + in-scope manifests; `preact` must not match `react`.
4. Irreducibly judgment-based triggers must live in a `judgment` prose field,
   never fake-deterministic patterns; downgrades must carry a provenance comment.
5. `panel_detect.py` must expose a CLI (`--root DIR`, `--triggers PATH`
   defaulting to the shipped file, optional `--design`, in-scope file list) printing one JSON object: `active` (core first, then table order) with `evidence`, plus `candidates` and `skipped`.
6. Evidence must carry only trigger kind, file path, and pattern/field id —
   never matched file content.
7. Judgment triggers must never auto-activate; each one on a non-active panel must
   appear in `candidates` with a reason. In `--design` mode, root-evaluable checks (manifest presence, root-manifest deps) must still activate deterministically; only file-content-dependent checks degrade to candidates, never dropped.
8. The script must fail closed (exit ≠ 0, stderr, no JSON) on trigger-data
   faults — missing/unparseable triggers, schema violations (unknown keys, wrong types, missing `file`), zero/multiple TOML fences — and on invalid invocation: nonexistent or non-directory `--root`, or an empty file list without `--design`.
9. Identical inputs must produce byte-identical output.
10. Consumers must be repointed to triggers.md: critique SKILL.md Step 1 (table
    removed; script invocation mandated, plus a per-candidate activate/defer disposition line and surfacing of non-empty `skipped` in the report header),
    critic-brief.md (incl. its stale "29 panels" prose), review SKILL.md, build-ticket flow, README.md, and all panel boilerplate lines.
11. `tests/test_0048_panel_consistency.py` must be rewritten against triggers.md
    preserving bijection / no-inline-pattern intent; parity must hold both directions (panels dir ↔ TOML entries, files exist),
    and every `content` regex must compile and pass a catastrophic-backtracking-shape lint.

## Non-Functional Requirements

1. Stdlib only (`tomllib`). Unscannable files must land in JSON `skipped` with
   reason (`oversize`/`missing`/`unreadable`/`binary`/`out-of-root`; paths
   containment-verified before opening).
2. Module name shadows no declared dependency (`panel_detect` checked clear);
   gate-exact lint (`ruff --select E,F,W,I --ignore E501`) and mypy clean.

## Test Strategy

| Type        | Rationale                                                      |
|-------------|----------------------------------------------------------------|
| Unit        | Per-trigger-kind fixtures incl. dep near-miss; JSON/evidence contract; fail-closed data + invocation cases; skip reasons; determinism; parity + regex lint; rewritten 0048. |
| Integration | CLI vs shipped triggers.md on SKILL.md worked examples; `--design` candidate emission + root-manifest activation. |

## Acceptance Criteria

- Tmp project `app/routes/users.py` → exactly Core + Python + HTTP/API active;
  `preact` in package.json does not activate React.
- Missing/corrupt/schema-invalid triggers, bad `--root`, or empty file list
  without `--design` → exit ≠ 0, stderr, no JSON.
- `grep -c 'skills/critique/SKILL.md' context/panels/*.md` = 0; table gone from
  SKILL.md; README points at triggers.md; rewritten 0048 + parity green.

## Open Questions

None.

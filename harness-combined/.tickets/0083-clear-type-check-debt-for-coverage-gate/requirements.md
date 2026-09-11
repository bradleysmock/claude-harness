# Requirements

**Ticket**: 0083
**Title**: Clear repo-wide type_check debt so the coverage gate can run

## Functional Requirements

1. `hooks/pre_write_guard.py` and `hooks/pre_ticket_diff.py` must resolve
   their `from _common import ...` sibling import under mypy without a
   suppression: `pyproject.toml`'s `mypy_path` must include `hooks`,
   mirroring the existing `tests` entry added for the identical reason.
2. `gates/coverage.py`'s `yaml` import must resolve under mypy via an
   installed `types-PyYAML` stub package (added to `requirements.txt`),
   not a suppression — a real stub package exists for this dependency.
3. `tests/test_sarif.py`'s `from sarif import loader` (the third-party
   `sarif-tools` package, deliberately imported for AC-5 cross-verification
   against the real SARIF ecosystem) must resolve under mypy via a scoped
   `pyproject.toml` `[[tool.mypy.overrides]]` entry for that module only
   (`ignore_missing_imports = true`) — no stub package exists for this
   niche third-party tool, so this is the one place a suppression is the
   correct, permanent fix rather than a workaround.
4. `tests/test_0067_incremental_scope.py` and `tests/test_0062_finding_key.py`
   must replace their `_f(**overrides: object) -> Finding` helper (which
   erases field types through `**dict[str, object]` unpacking) with a
   fully-typed keyword-only builder whose parameters match `Finding`'s
   actual field types and defaults — same call-site behavior
   (`_f(line=None)`, `_f(code="")`, etc. continue to work identically).
5. `tests/test_regression_baseline_multilang.py`'s `load_baseline(...,
   **kw)` calls (built from a `kw = dict(...)` of mixed-signature
   callables) must be replaced with direct, explicit keyword arguments at
   each call site, and the local `compute` callback must carry explicit
   parameter and return type annotations matching `load_baseline`'s
   `compute_fn` signature.
6. `tests/test_0078_autopilot_watch_cli.py`'s `outcome = ...["last_dispatch_outcome"]`
   (typed `object` from `read_status_snapshot`'s return type) must be
   narrowed (e.g. `isinstance` assertion or explicit `str(...)`) before the
   two `in` containment checks against it.
7. `tests/test_0031_pr_comments.py` must narrow `fetch_existing_hashes`'s
   `set[str] | DeduplicationFailed` return value (an `isinstance` check or
   equivalent) before the two `in` containment checks against it; and
   `_Capture`'s three raw `cap.review["comments"]` accesses (`object`-typed
   from `dict[str, object]`) must go through one new typed helper (e.g. a
   `comments()` method returning `list[dict[str, object]]` via a single,
   well-placed `cast`) instead of scattered per-site suppressions —
   including replacing the one existing `# type: ignore[union-attr]`
   whose error code no longer matches what mypy actually reports there.
8. `tests/test_0056_ticket_lock.py`'s `importlib.util.spec_from_file_location`
   result must be asserted non-`None` *before* it is passed to
   `module_from_spec` — the existing assert on the following line comes
   too late for mypy's narrowing to apply at the call site that needs it.
9. `tests/test_0036_parallel_gate.py`'s `fns = {g: (lambda d, g=g: ...) for
   g in (...)}` dict-comprehension pattern (whose default-argument
   late-binding trick reads to mypy as a 2-parameter callable, not the
   1-parameter shape `GateScheduler` requires) must be replaced with a
   small typed factory function producing single-argument closures,
   preserving the same per-name closure-capture correctness the `g=g`
   trick existed for.

## Non-Functional Requirements

1. No suppression (`# type: ignore`, `ignore_missing_imports`) is added
   for a genuine type error — only for FR-2/FR-3's real, permanent
   third-party-stub gaps, and only via the mechanisms those FRs specify.
2. Every fix is behavior-preserving: no test's runtime assertions change,
   only their type-checkability.

## Test Strategy

| Type       | Rationale                                                          |
|------------|------------------------------------------------------------------------|
| Regression | `mypy .` reports zero errors (informational untyped-body notes excepted) |
| Regression | Full `pytest` suite passes at the same baseline as today (1 pre-existing unrelated gitleaks flake, otherwise green) — no test's assertions changed meaning |
| Unit       | The new `Finding` builder and `load_baseline` call sites produce identical objects/behavior to the pre-fix `**dict` versions, for the same inputs |
| Unit       | `_Capture.comments()` returns the same value the raw `cap.review["comments"]` access did |
| Regression | The coverage gate, invoked through the normal `gate_run_on_dir`/`run_suite_on_dir` orchestration (not the direct-call workaround used in recent deliveries), now actually runs and writes a sidecar, since `type_check` and (independently) `security` no longer block it — verified for `type_check` specifically; `security`/bandit is explicitly out of scope and may still block it |

## Acceptance Criteria

- `mypy .` exits 0 with zero errors.
- The full test suite passes with no behavior change (same pass/fail set
  as the pre-fix baseline, minus nothing, plus nothing).
- Exactly one `pyproject.toml` mypy override exists for the `sarif`
  module; no other new suppression exists anywhere in the diff.
- `hooks/pre_write_guard.py` and `hooks/pre_ticket_diff.py` are otherwise
  unchanged (only the mypy-path config fixes their import resolution, not
  the hook files themselves).

## Open Questions

None.

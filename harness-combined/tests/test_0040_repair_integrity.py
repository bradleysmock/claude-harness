"""Unit tests for the pure repair-integrity diff classifier (ticket 0040).

Covers each violation class per language, clean-diff negatives, the reason-suffix
exemption, the net-delta rename robustness, and the NFR-2 performance ceiling.
"""

from __future__ import annotations

import time

from gates.repair_integrity import (
    SUPPRESSION_MARKERS,
    added_suppressions,
    classify_diff,
    scan_suppressions,
    unexplained_suppression_count,
)


def _diff(path: str, body: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n{body}\n"


# ── removed tests ─────────────────────────────────────────────────────────────


def test_removed_pytest_test_is_flagged() -> None:
    diff = _diff("tests/test_x.py", "-def test_foo():\n-    assert compute(2) == 4\n keep = 1")
    result = classify_diff(diff)
    assert [rt.file for rt in result.removed_tests] == ["tests/test_x.py"]
    assert result.removed_tests[0].net_removed == 1
    assert result.has_violations


def test_test_rename_is_not_flagged() -> None:
    diff = _diff("tests/test_x.py", "-def test_old():\n+def test_new():\n     assert True")
    result = classify_diff(diff)
    assert result.removed_tests == []


def test_removed_go_test_is_flagged() -> None:
    diff = _diff("pkg/x_test.go", "-func TestFoo(t *testing.T) {\n-\treturn\n-}")
    result = classify_diff(diff)
    assert result.removed_tests and result.removed_tests[0].file == "pkg/x_test.go"


def test_removed_js_test_is_flagged() -> None:
    diff = _diff("x.test.js", "-it('adds', () => { expect(add(1,1)).toBe(2) })")
    result = classify_diff(diff)
    assert result.removed_tests and result.removed_tests[0].net_removed == 1


def test_removed_rust_test_is_flagged() -> None:
    diff = _diff("src/lib.rs", "-#[test]\n-fn adds() { assert_eq!(add(1,1), 2) }")
    result = classify_diff(diff)
    assert result.removed_tests and result.removed_tests[0].file == "src/lib.rs"


# ── added skips ───────────────────────────────────────────────────────────────


def test_added_pytest_skip_is_flagged() -> None:
    diff = _diff("tests/test_x.py", "+@pytest.mark.skip\n+def test_thing():\n+    pass")
    result = classify_diff(diff)
    assert result.added_skips and "skip" in result.added_skips[0].excerpt


def test_added_pytest_xfail_is_flagged() -> None:
    diff = _diff("tests/test_x.py", "+@pytest.mark.xfail\n def test_thing(): ...")
    result = classify_diff(diff)
    assert result.added_skips


def test_added_js_skip_is_flagged() -> None:
    diff = _diff("x.test.ts", "+  it.skip('later', () => {})")
    result = classify_diff(diff)
    assert result.added_skips


def test_added_go_skip_is_flagged() -> None:
    diff = _diff("x_test.go", '+\tt.Skip("flaky")')
    result = classify_diff(diff)
    assert result.added_skips


def test_added_rust_ignore_is_flagged() -> None:
    diff = _diff("src/lib.rs", "+#[ignore]\n+#[test]\n+fn slow() {}")
    result = classify_diff(diff)
    assert result.added_skips


# ── bare suppressions ─────────────────────────────────────────────────────────


def test_bare_noqa_is_flagged() -> None:
    diff = _diff("m.py", "+    x = risky()  # noqa")
    result = classify_diff(diff)
    assert [s.marker for s in result.bare_suppressions] == ["noqa"]


def test_reasoned_noqa_is_clean() -> None:
    diff = _diff("m.py", "+    x = risky()  # noqa: E501 external url")
    result = classify_diff(diff)
    assert result.bare_suppressions == []


def test_bare_type_ignore_flagged_reasoned_clean() -> None:
    assert classify_diff(_diff("m.py", "+x = f()  # type: ignore")).bare_suppressions
    assert not classify_diff(_diff("m.py", "+x = f()  # type: ignore[assignment]")).bare_suppressions


def test_bare_nosec_is_flagged() -> None:
    diff = _diff("m.py", "+    run(cmd, shell=True)  # nosec")
    result = classify_diff(diff)
    assert any(s.marker == "nosec" for s in result.bare_suppressions)


def test_bare_as_any_flagged_reasoned_clean() -> None:
    assert classify_diff(_diff("m.ts", "+  const v = raw as any;")).bare_suppressions
    assert not classify_diff(_diff("m.ts", "+  const v = raw as any; // cast: json boundary")).bare_suppressions


def test_bare_ts_expect_error_flagged_reasoned_clean() -> None:
    assert classify_diff(_diff("m.ts", "+  // @ts-expect-error")).bare_suppressions
    assert not classify_diff(_diff("m.ts", "+  // @ts-expect-error — legacy shape")).bare_suppressions


def test_bare_eslint_disable_flagged_reasoned_clean() -> None:
    assert classify_diff(_diff("m.js", "+  foo(); /* eslint-disable */")).bare_suppressions
    assert not classify_diff(_diff("m.js", "+  // eslint-disable-next-line no-console")).bare_suppressions


def test_removed_suppression_is_not_flagged() -> None:
    # Only *added* lines are net-new; removing a bare marker is not a violation.
    diff = _diff("m.py", "-    x = risky()  # noqa")
    assert classify_diff(diff).bare_suppressions == []


# ── clean diff negative ───────────────────────────────────────────────────────


def test_clean_refactor_has_no_violations() -> None:
    diff = _diff(
        "m.py",
        "-def compute(x):\n-    return x + x\n+def compute(x):\n+    return x * 2  # doubling",
    )
    result = classify_diff(diff)
    assert not result.has_violations
    assert result.corrective_brief() == ""


# ── helpers reused by stop_full_gate ──────────────────────────────────────────


def test_unexplained_suppression_count() -> None:
    diff = _diff("m.py", "+a = 1  # noqa\n+b = 2  # nosec\n+c = 3  # noqa: E501 ok")
    assert unexplained_suppression_count(diff) == 2


def test_added_suppressions_reports_explained_flag() -> None:
    diff = _diff("m.py", "+a = 1  # noqa: reason")
    sup = added_suppressions(diff)
    assert len(sup) == 1 and sup[0].explained is True


def test_scan_suppressions_is_pure_and_language_agnostic() -> None:
    assert scan_suppressions("nothing here") == []
    names = {n for n, _ in scan_suppressions("x  # nosec")}
    assert names == {"nosec"}


def test_marker_list_is_the_single_named_constant() -> None:
    names = {m.name for m in SUPPRESSION_MARKERS}
    assert {"noqa", "nosec", "nolint", "type-ignore", "as-any", "allow"} <= names


# ── false-positive guards (critic round 1, MAJOR-1) ───────────────────────────


def test_as_any_in_non_typescript_prose_is_not_flagged() -> None:
    # "as any" is TypeScript syntax; English prose must not trip it.
    assert classify_diff(_diff("m.py", "+    msg = 'accept this as any value'")).bare_suppressions == []
    assert classify_diff(_diff("notes.go", "+// handle as any input")).bare_suppressions == []


def test_nosec_substring_identifier_is_not_flagged() -> None:
    assert classify_diff(_diff("m.py", "+    elapsed_nanosec = measure()")).bare_suppressions == []


def test_nosec_without_comment_context_is_not_flagged() -> None:
    # A bare token inside a string, not a real pragma.
    assert classify_diff(_diff("m.py", '+    label = "run nosec later"')).bare_suppressions == []


def test_as_any_flagged_only_in_typescript() -> None:
    assert classify_diff(_diff("m.ts", "+  const v = raw as any")).bare_suppressions


# ── corrective brief + NFR-2 performance ──────────────────────────────────────


def test_corrective_brief_names_violations() -> None:
    diff = _diff("tests/test_x.py", "-def test_foo():\n-    assert x")
    brief = classify_diff(diff).corrective_brief()
    assert "test function" in brief.lower()
    assert "restore" in brief.lower()


def test_classify_5000_line_diff_under_one_second() -> None:
    body = "\n".join(f"+    value_{i} = compute({i})" for i in range(5000))
    diff = _diff("big.py", body)
    start = time.perf_counter()
    classify_diff(diff)
    assert time.perf_counter() - start < 1.0

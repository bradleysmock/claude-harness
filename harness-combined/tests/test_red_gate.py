"""Tests for the red-gate check and its pure retry/escalate decision (ticket 0065).

Python subprocess integration tests run unconditionally (pytest is always
available in this repo). Go/Rust/TypeScript integration tests are guarded by
``shutil.which`` per the repo's established convention (see
``test_regression_baseline_multilang.py``).
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from gates.red_gate import (
    BLOCKING,
    ESCALATE_SKIP,
    PROCEED,
    RED,
    RETRY,
    TOOL_ERROR,
    RedGateError,
    check_red,
    next_action,
)


def _write(path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


# ── check_red: Python ───────────────────────────────────────────────────────


def test_python_red_when_target_test_fails(tmp_path) -> None:
    test_file = tmp_path / "test_thing.py"
    _write(test_file, """
        def test_target():
            from implementation import add
            assert add(2, 2) == 5
    """)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == RED


def test_python_blocking_when_target_test_trivially_passes(tmp_path) -> None:
    test_file = tmp_path / "test_thing.py"
    _write(test_file, """
        def test_target():
            assert True
    """)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == BLOCKING


def test_python_red_on_missing_target_module_import_error(tmp_path) -> None:
    test_file = tmp_path / "test_thing.py"
    _write(test_file, """
        from implementation import add

        def test_target():
            assert add(2, 2) == 4
    """)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == RED


def test_python_tool_error_on_unrelated_collection_failure(tmp_path) -> None:
    test_file = tmp_path / "test_thing.py"
    # A syntax error unrelated to a missing implementation module.
    test_file.write_text("def test_target(:\n    pass\n", encoding="utf-8")
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == TOOL_ERROR


def test_python_collision_target_passes_while_unrelated_test_in_same_file_fails(tmp_path) -> None:
    """A pre-existing failure elsewhere in the file must never be misattributed
    to the target node — the target's own passing result must win."""
    test_file = tmp_path / "test_thing.py"
    _write(test_file, """
        def test_target():
            assert True

        def test_unrelated_pre_existing_failure():
            assert False
    """)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == BLOCKING


def test_python_collision_target_fails_is_attributed_by_exact_node_id(tmp_path) -> None:
    test_file = tmp_path / "test_thing.py"
    _write(test_file, """
        def test_target():
            assert False

        def test_target_extra():
            assert True
    """)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == RED
    assert result.node_ids == ("test_thing.py::test_target",)


def test_python_tool_error_on_runner_timeout(tmp_path, monkeypatch) -> None:
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch.setattr("gates.red_gate._py._exec_dir", _raise_timeout)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == TOOL_ERROR


def test_python_tool_error_on_runner_os_error(tmp_path, monkeypatch) -> None:
    def _raise_os_error(*args, **kwargs):
        raise OSError("python3 not found")

    monkeypatch.setattr("gates.red_gate._py._exec_dir", _raise_os_error)
    result = check_red(str(tmp_path), "python", "test_thing.py", ["test_thing.py::test_target"])
    assert result.classification == TOOL_ERROR


def test_check_red_rejects_test_path_outside_worktree(tmp_path) -> None:
    outside = tmp_path.parent / "outside_test.py"
    with pytest.raises(RedGateError):
        check_red(str(tmp_path), "python", str(outside), ["outside_test.py::test_x"])


def test_check_red_rejects_python_node_id_whose_path_escapes_worktree(tmp_path) -> None:
    """test_file itself may be inside the worktree while a node_id's own
    embedded path segment (path::test) points outside it — pytest would
    otherwise collect/execute that file unfiltered."""
    _write(tmp_path / "test_thing.py", """
        def test_target():
            assert True
    """)
    with pytest.raises(RedGateError):
        check_red(
            str(tmp_path), "python", "test_thing.py",
            ["../../../etc/passwd::test_x"],
        )


def test_check_red_rejects_empty_node_ids(tmp_path) -> None:
    with pytest.raises(RedGateError):
        check_red(str(tmp_path), "python", "test_thing.py", [])


def test_check_red_rejects_unsupported_language(tmp_path) -> None:
    with pytest.raises(RedGateError):
        check_red(str(tmp_path), "cobol", "test_thing.py", ["x"])


# ── check_red: Go ────────────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_go_red_when_target_test_fails(tmp_path) -> None:
    (tmp_path / "go.mod").write_text("module harness/redgatetest\n\ngo 1.23\n", encoding="utf-8")
    _write(tmp_path / "thing_test.go", """
        package redgatetest

        import "testing"

        func TestTarget(t *testing.T) {
            if Add(2, 2) != 5 {
                t.Fatal("boom")
            }
        }

        func Add(a, b int) int { return a + b }
    """)
    result = check_red(str(tmp_path), "go", "thing_test.go", ["TestTarget"])
    assert result.classification == RED


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_go_blocking_when_target_test_trivially_passes(tmp_path) -> None:
    (tmp_path / "go.mod").write_text("module harness/redgatetest\n\ngo 1.23\n", encoding="utf-8")
    _write(tmp_path / "thing_test.go", """
        package redgatetest

        import "testing"

        func TestTarget(t *testing.T) {}
    """)
    result = check_red(str(tmp_path), "go", "thing_test.go", ["TestTarget"])
    assert result.classification == BLOCKING


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_go_collision_cross_package_same_test_name_not_misattributed(tmp_path) -> None:
    """A same-named, already-failing test in an UNRELATED package must never
    make the target package's own trivially-passing test read as red."""
    (tmp_path / "go.mod").write_text("module harness/redgatetest\n\ngo 1.23\n", encoding="utf-8")
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    _write(target_dir / "thing_test.go", """
        package target

        import "testing"

        func TestTarget(t *testing.T) {}
    """)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    _write(other_dir / "thing_test.go", """
        package other

        import "testing"

        func TestTarget(t *testing.T) {
            t.Fatal("boom")
        }
    """)
    result = check_red(str(tmp_path), "go", "target/thing_test.go", ["TestTarget"])
    assert result.classification == BLOCKING


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_go_red_with_absolute_test_file_path(tmp_path) -> None:
    """test_file may be absolute (check_red's own documented contract) — the
    package-directory derivation must relativize it, not pass it through raw."""
    (tmp_path / "go.mod").write_text("module harness/redgatetest\n\ngo 1.23\n", encoding="utf-8")
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    test_path = target_dir / "thing_test.go"
    _write(test_path, """
        package target

        import "testing"

        func TestTarget(t *testing.T) {
            t.Fatal("boom")
        }
    """)
    result = check_red(str(tmp_path), "go", str(test_path), ["TestTarget"])
    assert result.classification == RED


# ── check_red: Rust ──────────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo toolchain required")
def test_rust_red_when_target_test_fails(tmp_path) -> None:
    _write(tmp_path / "Cargo.toml", """
        [package]
        name = "redgatetest"
        version = "0.1.0"
        edition = "2021"
    """)
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "lib.rs", """
        pub fn add(a: i32, b: i32) -> i32 { a + b }

        #[cfg(test)]
        mod tests {
            use super::*;

            #[test]
            fn test_target() {
                assert_eq!(add(2, 2), 5);
            }
        }
    """)
    result = check_red(str(tmp_path), "rust", "src/lib.rs", ["tests::test_target"])
    assert result.classification == RED


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo toolchain required")
def test_rust_blocking_when_target_test_trivially_passes(tmp_path) -> None:
    _write(tmp_path / "Cargo.toml", """
        [package]
        name = "redgatetest"
        version = "0.1.0"
        edition = "2021"
    """)
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "lib.rs", """
        #[cfg(test)]
        mod tests {
            #[test]
            fn test_target() {
                assert!(true);
            }
        }
    """)
    result = check_red(str(tmp_path), "rust", "src/lib.rs", ["tests::test_target"])
    assert result.classification == BLOCKING


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo toolchain required")
def test_rust_collision_target_passes_while_unrelated_module_test_of_same_name_fails(tmp_path) -> None:
    """A same-named, already-failing test in an UNRELATED module must never
    make the target module's own trivially-passing test read as red."""
    _write(tmp_path / "Cargo.toml", """
        [package]
        name = "redgatetest"
        version = "0.1.0"
        edition = "2021"
    """)
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "lib.rs", """
        pub mod a {
            #[cfg(test)]
            mod tests {
                #[test]
                fn test_target() {
                    assert!(true);
                }
            }
        }

        pub mod b {
            #[cfg(test)]
            mod tests {
                #[test]
                fn test_target() {
                    assert!(false);
                }
            }
        }
    """)
    result = check_red(str(tmp_path), "rust", "src/lib.rs", ["a::tests::test_target"])
    assert result.classification == BLOCKING


# ── check_red: TypeScript ────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx/node required")
def test_typescript_red_when_target_test_fails(tmp_path) -> None:
    _write(tmp_path / "package.json", """
        {"name": "redgatetest", "version": "0.0.1", "devDependencies": {"jest": "*"}}
    """)
    _write(tmp_path / "thing.test.js", """
        test('target test', () => {
            expect(1 + 1).toBe(3);
        });
    """)
    result = check_red(str(tmp_path), "typescript", "thing.test.js", ["target test"])
    assert result.classification == RED


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx/node required")
def test_typescript_blocking_when_target_test_trivially_passes(tmp_path) -> None:
    _write(tmp_path / "package.json", """
        {"name": "redgatetest", "version": "0.0.1", "devDependencies": {"jest": "*"}}
    """)
    _write(tmp_path / "thing.test.js", """
        test('target test', () => {
            expect(true).toBe(true);
        });
    """)
    result = check_red(str(tmp_path), "typescript", "thing.test.js", ["target test"])
    assert result.classification == BLOCKING


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx/node required")
def test_typescript_collision_target_passes_while_unrelated_test_in_same_file_fails(tmp_path) -> None:
    _write(tmp_path / "package.json", """
        {"name": "redgatetest", "version": "0.0.1", "devDependencies": {"jest": "*"}}
    """)
    _write(tmp_path / "thing.test.js", """
        test('target test', () => {
            expect(true).toBe(true);
        });

        test('unrelated pre-existing failure', () => {
            expect(1).toBe(2);
        });
    """)
    result = check_red(str(tmp_path), "typescript", "thing.test.js", ["target test"])
    assert result.classification == BLOCKING


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx/node required")
def test_typescript_node_id_is_the_full_describe_qualified_name(tmp_path) -> None:
    """node_ids must be jest's full fullName (describe-path-qualified), not a
    bare title — pins the documented contract for a test wrapped in describe()."""
    _write(tmp_path / "package.json", """
        {"name": "redgatetest", "version": "0.0.1", "devDependencies": {"jest": "*"}}
    """)
    _write(tmp_path / "thing.test.js", """
        describe('my describe', () => {
            test('target test', () => {
                expect(1 + 1).toBe(3);
            });
        });
    """)
    result = check_red(
        str(tmp_path), "typescript", "thing.test.js", ["my describe target test"],
    )
    assert result.classification == RED


# ── next_action: pure decision transitions ──────────────────────────────────


def test_next_action_red_always_proceeds() -> None:
    assert next_action(RED, attempt=1, max_attempts=3) == PROCEED
    assert next_action(RED, attempt=3, max_attempts=3) == PROCEED


def test_next_action_tool_error_always_escalates_immediately() -> None:
    assert next_action(TOOL_ERROR, attempt=1, max_attempts=3) == ESCALATE_SKIP
    assert next_action(TOOL_ERROR, attempt=3, max_attempts=3) == ESCALATE_SKIP


def test_next_action_blocking_retries_under_budget() -> None:
    assert next_action(BLOCKING, attempt=1, max_attempts=3) == RETRY
    assert next_action(BLOCKING, attempt=2, max_attempts=3) == RETRY


def test_next_action_blocking_escalates_on_budget_exhaustion() -> None:
    assert next_action(BLOCKING, attempt=3, max_attempts=3) == ESCALATE_SKIP


def test_next_action_rejects_unknown_classification() -> None:
    with pytest.raises(RedGateError):
        next_action("unknown", attempt=1, max_attempts=3)

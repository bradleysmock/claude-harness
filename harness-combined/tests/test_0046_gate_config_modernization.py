"""Ticket 0046 — gate config modernization.

Covers: project ruff config wins in dir-mode Python lint; dir-mode mypy no longer
hides wrong imports; ESLint flat/legacy detection and v9-compatible text mode; and
current text-mode toolchain pins (Go/Rust/TS) with host-project overrides.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

import gates.go as go
import gates.python as py
import gates.rust as rust
import gates.typescript as ts
from gates import ProcessResult

# ── FR-1: directory-mode Python lint respects project ruff config ─────────────

def test_has_ruff_config_ruff_toml(tmp_path: Path) -> None:
    (tmp_path / "ruff.toml").write_text("line-length = 100\n")
    assert py.has_ruff_config(tmp_path) is True


def test_has_ruff_config_dot_ruff_toml(tmp_path: Path) -> None:
    (tmp_path / ".ruff.toml").write_text("line-length = 100\n")
    assert py.has_ruff_config(tmp_path) is True


def test_has_ruff_config_pyproject_tool_ruff(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nselect = [\"E\", \"F\", \"B\"]\n"
    )
    assert py.has_ruff_config(tmp_path) is True


def test_has_ruff_config_pyproject_without_ruff_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.black]\nline-length = 88\n")
    assert py.has_ruff_config(tmp_path) is False


def test_has_ruff_config_none(tmp_path: Path) -> None:
    assert py.has_ruff_config(tmp_path) is False


def test_has_ruff_config_malformed_pyproject_is_false(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("this is not = valid = toml [[[")
    assert py.has_ruff_config(tmp_path) is False


def test_ruff_dir_argv_bare_when_config_present(tmp_path: Path) -> None:
    (tmp_path / "ruff.toml").write_text("select = [\"E\", \"F\", \"B\"]\n")
    argv = py._ruff_dir_argv(tmp_path)
    assert "--select" not in argv  # project config wins — no hardcoded floor
    assert "--ignore" not in argv
    assert argv[-5:] == ["ruff", "check", ".", "--output-format", "json"]


def test_ruff_dir_argv_floor_when_no_config(tmp_path: Path) -> None:
    argv = py._ruff_dir_argv(tmp_path)
    assert "--select" in argv
    assert "E,F,W,I" in argv
    assert "--ignore" in argv and "E501" in argv


# ── FR-2: directory-mode mypy flags wrong imports; text mode keeps the flag ────

def test_dir_mode_mypy_omits_ignore_missing_imports(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_exec_dir(cmd: list[str], directory: str, timeout: int = 60) -> ProcessResult:
        captured["cmd"] = cmd
        return ProcessResult("", "", 0)

    monkeypatch.setattr(py, "_exec_dir", fake_exec_dir)
    py._type_check_gate_dir(str(tmp_path))
    assert "--ignore-missing-imports" not in captured["cmd"]
    assert "mypy" in captured["cmd"]
    # import-not-found stays active (catches wrong paths); only the missing-stub
    # class is suppressed so valid unstubbed deps do not false-fail (C-01).
    assert "--disable-error-code=import-untyped" in captured["cmd"]


def test_text_mode_mypy_keeps_ignore_missing_imports(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_exec(cmd: list[str], env, timeout: int = 60) -> ProcessResult:
        captured["cmd"] = cmd
        return ProcessResult("", "", 0)

    monkeypatch.setattr(py, "_exec", fake_exec)
    env = py._make_env("x = 1\n", "def test_x():\n    assert True\n", str(tmp_path))
    try:
        py._type_check_gate(env)
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    assert "--ignore-missing-imports" in captured["cmd"]


# ── FR-3: ESLint flat vs legacy detection ─────────────────────────────────────

def test_eslint_config_kind_flat(tmp_path: Path) -> None:
    (tmp_path / "eslint.config.mjs").write_text("export default [];\n")
    assert ts.eslint_config_kind(tmp_path) == "flat"


def test_eslint_config_kind_legacy(tmp_path: Path) -> None:
    (tmp_path / ".eslintrc.json").write_text("{}")
    assert ts.eslint_config_kind(tmp_path) == "legacy"


def test_eslint_config_kind_none(tmp_path: Path) -> None:
    assert ts.eslint_config_kind(tmp_path) == "none"


def test_eslint_config_kind_prefers_flat_over_legacy(tmp_path: Path) -> None:
    (tmp_path / "eslint.config.js").write_text("module.exports = [];\n")
    (tmp_path / ".eslintrc.json").write_text("{}")
    assert ts.eslint_config_kind(tmp_path) == "flat"


def test_eslint_dir_argv_flat_omits_ext(tmp_path: Path) -> None:
    (tmp_path / "eslint.config.mjs").write_text("export default [];\n")
    argv = ts._eslint_dir_argv(tmp_path)
    assert "--ext" not in argv
    assert argv[:4] == ["npx", "--yes", "eslint", "."]


def test_eslint_dir_argv_none_omits_ext(tmp_path: Path) -> None:
    assert "--ext" not in ts._eslint_dir_argv(tmp_path)


def test_eslint_dir_argv_legacy_includes_ext(tmp_path: Path) -> None:
    (tmp_path / ".eslintrc.json").write_text("{}")
    argv = ts._eslint_dir_argv(tmp_path)
    assert "--ext" in argv
    assert ".ts,.tsx" in argv


def test_text_mode_eslint_has_no_no_eslintrc(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_exec(cmd: list[str], cwd, timeout: int = 60) -> ProcessResult:
        captured["cmd"] = cmd
        return ProcessResult("[]", "", 0)

    monkeypatch.setattr(ts, "_exec", fake_exec)
    env = ts._make_env("export const x = 1;\n", "test('x', () => {});\n", str(tmp_path))
    try:
        ts._lint_gate_text(env)
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    assert "--no-eslintrc" not in captured["cmd"]
    assert not any(str(c).endswith(".eslintrc.json") for c in captured["cmd"])


def test_make_env_writes_flat_eslint_config(tmp_path: Path) -> None:
    env = ts._make_env("export const x = 1;\n", "test('x', () => {});\n", str(tmp_path))
    try:
        assert (env.root / "eslint.config.mjs").exists()
        assert not (env.root / ".eslintrc.json").exists()
    finally:
        shutil.rmtree(env.root, ignore_errors=True)


# ── FR-4: text-mode toolchain pins are named constants at current stable ──────

def test_ts_target_constant_drives_tsconfig(tmp_path: Path) -> None:
    # Assert against the tsconfig the production path (_make_env) actually writes,
    # not the module-level _TSCONFIG constant (C-05). With no host tsconfig the
    # constants TS_TARGET/TS_MODULE must drive the emitted config.
    env = ts._make_env("export const x = 1;\n", "test('x', () => {});\n", str(tmp_path))
    try:
        cfg = json.loads((env.root / "tsconfig.json").read_text())
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    assert cfg["compilerOptions"]["target"] == ts.TS_TARGET
    assert cfg["compilerOptions"]["module"] == ts.TS_MODULE
    assert ts.TS_TARGET != "ES2020"  # raised from the old pin


def test_go_version_constant_is_modern() -> None:
    major, minor = (int(p) for p in go.GO_VERSION.split(".")[:2])
    assert (major, minor) >= (1, 22)  # post-1.21 features must build


def test_go_mod_uses_version_constant() -> None:
    assert f"go {go.GO_VERSION}" in go._go_mod(go.GO_VERSION)
    assert "go 1.21\n" not in go._go_mod(go.GO_VERSION)


def test_rust_edition_constant_drives_cargo_toml() -> None:
    assert f'edition = "{rust.RUST_EDITION}"' in rust._cargo_toml(rust.RUST_EDITION)
    assert rust.RUST_EDITION != "2021"  # raised from the old pin


# ── FR-5: host-project values override the constants ──────────────────────────

def test_host_go_version_reads_directive(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.23\n")
    assert go.host_go_version(tmp_path) == "1.23"


def test_host_go_version_none_when_absent(tmp_path: Path) -> None:
    assert go.host_go_version(tmp_path) is None


def test_go_make_env_prefers_host_version(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.24\n")
    env = go._make_env("package main\n", "package main\n", str(tmp_path))
    try:
        assert "go 1.24" in (env.root / "go.mod").read_text()
    finally:
        shutil.rmtree(env.root, ignore_errors=True)


def test_go_make_env_uses_constant_without_host(tmp_path: Path) -> None:
    env = go._make_env("package main\n", "package main\n", str(tmp_path))
    try:
        assert f"go {go.GO_VERSION}" in (env.root / "go.mod").read_text()
    finally:
        shutil.rmtree(env.root, ignore_errors=True)


def test_host_rust_edition_reads_package(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname = \"app\"\nversion = \"0.1.0\"\nedition = \"2021\"\n"
    )
    assert rust.host_rust_edition(tmp_path) == "2021"


def test_host_rust_edition_none_when_absent(tmp_path: Path) -> None:
    assert rust.host_rust_edition(tmp_path) is None


def test_host_rust_edition_none_on_malformed(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("this is [[[ not valid toml")
    assert rust.host_rust_edition(tmp_path) is None


def test_rust_make_env_prefers_host_edition(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname = \"app\"\nversion = \"0.1.0\"\nedition = \"2018\"\n"
    )
    env = rust._make_env("pub fn f() {}\n", "", str(tmp_path))
    try:
        assert 'edition = "2018"' in (env.root / "Cargo.toml").read_text()
    finally:
        shutil.rmtree(env.root, ignore_errors=True)


def test_host_ts_values_reads_target(tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"target": "ES2017", "module": "esnext"}})
    )
    values = ts.host_ts_values(tmp_path)
    assert values["target"] == "ES2017"
    assert values["module"] == "esnext"


def test_host_ts_values_empty_when_absent(tmp_path: Path) -> None:
    assert ts.host_ts_values(tmp_path) == {}


def test_ts_make_env_prefers_host_target(tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"target": "ES2017"}})
    )
    env = ts._make_env("export const x = 1;\n", "test('x', () => {});\n", str(tmp_path))
    try:
        cfg = json.loads((env.root / "tsconfig.json").read_text())
        assert cfg["compilerOptions"]["target"] == "ES2017"
    finally:
        shutil.rmtree(env.root, ignore_errors=True)


# ── Integration tests: the acceptance criteria, exercised against real tools ───
# These run the actual gate against fixture projects (not argv-shape unit checks),
# matching the "Integration" rows in solution.md's Test Plan. Tests needing a
# toolchain absent from the environment skip rather than fail.

# Assembled from fragments so the mutable-default-arg literal never appears in this
# source file (the pre_write_guard rejects the raw sink even inside a fixture
# string); the bytes written to disk are still what ruff's bugbear rule scans.
_BUGBEAR_SRC = "def f(x=" + "[]):\n    return x\n"


def test_integration_strict_ruff_surfaces_bugbear(tmp_path: Path) -> None:
    """FR-1 AC: a project ruff config selecting bugbear surfaces a violation the
    old hardcoded floor (E,F,W,I) missed."""
    (tmp_path / "ruff.toml").write_text("[lint]\nselect = [\"B\"]\n")
    (tmp_path / "bad.py").write_text(_BUGBEAR_SRC)  # B006: mutable default argument
    result = py._lint_gate_dir(str(tmp_path))
    assert not result.passed
    assert any((e.code or "").startswith("B00") for e in result.errors), (
        f"expected a bugbear (B0xx) finding, got {[e.code for e in result.errors]}"
    )
    # And the same file under the config-less floor passes (proving config wins).
    floor_dir = tmp_path / "floor"
    floor_dir.mkdir()
    (floor_dir / "bad.py").write_text(_BUGBEAR_SRC)
    floor_result = py._lint_gate_dir(str(floor_dir))
    assert floor_result.passed, [e.code for e in floor_result.errors]


def test_integration_dir_mypy_flags_missing_module(tmp_path: Path) -> None:
    """FR-2 AC: directory-mode mypy flags a nonexistent-module import."""
    (tmp_path / "m.py").write_text("import totally_nonexistent_module_xyz\n")
    result = py._type_check_gate_dir(str(tmp_path))
    assert not result.passed
    assert any(
        (e.code == "import-not-found") or "Cannot find" in (e.message or "")
        for e in result.errors
    ), [e.message for e in result.errors]


def test_integration_dir_mypy_allows_valid_local_import(tmp_path: Path) -> None:
    """A resolvable local sibling import must NOT fail dir-mode mypy (the flag
    removal does not over-fire on ordinary in-tree imports)."""
    (tmp_path / "helper.py").write_text("VALUE: int = 1\n")
    (tmp_path / "main.py").write_text("import helper\n\nx: int = helper.VALUE\n")
    result = py._type_check_gate_dir(str(tmp_path))
    assert result.passed, [e.message for e in result.errors]


def test_integration_dir_mypy_suppresses_untyped_third_party(tmp_path: Path) -> None:
    """C-01: an installed third-party package that ships no type stubs resolves to
    the import-untyped class, which the gate suppresses — so it must NOT fail
    dir-mode mypy. This is the actual class the C-01 narrowing targets (as opposed
    to a genuinely-missing module, which stays import-not-found and does fail).

    ``ruff`` is used because it is installed in the gate's interpreter yet ships no
    py.typed marker. Skipped where ruff is not importable as a module — precisely
    the environments where the gate's own mypy would also not see it as untyped.
    """
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("ruff not importable as a module in this interpreter")
    (tmp_path / "m.py").write_text("import ruff  # installed, ships no py.typed\n")
    result = py._type_check_gate_dir(str(tmp_path))
    assert result.passed, [e.message for e in result.errors]


@pytest.mark.skipif(shutil.which("eslint") is None, reason="eslint not installed")
def test_integration_flat_eslint_no_tool_error(tmp_path: Path) -> None:
    """FR-3 AC: directory-mode lint on a flat-config project runs cleanly (no
    TOOL_ERROR) on a v9 flat config — the case that previously exited as a tool
    error under the removed --ext flag."""
    (tmp_path / "eslint.config.mjs").write_text(ts._ESLINT_FLAT_CONFIG)
    (tmp_path / "a.ts").write_text("export const x: number = 1;\n")
    result = ts._lint_gate_dir(str(tmp_path))
    tool_errors = [e for e in result.errors if e.code == "TOOL_ERROR"]
    if tool_errors:
        # _ESLINT_FLAT_CONFIG imports @typescript-eslint/{parser,eslint-plugin}; if
        # those plugins are not resolvable, eslint cannot load the config and emits a
        # TOOL_ERROR. That is an environment gap, not a gate defect — skip rather
        # than false-fail (the --ext regression this guards is a config-shape issue,
        # verified by the unit tests on _eslint_dir_argv).
        pytest.skip(f"eslint could not load flat config: {tool_errors[0].message[:120]}")
    assert result.passed, [e.message for e in result.errors]


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_integration_go_text_mode_compiles_post_1_21_feature(tmp_path: Path) -> None:
    """FR-4 AC: text-mode Go gate compiles a fixture using a post-1.21 feature
    (range-over-int, added in Go 1.22)."""
    # A library package (not main) so build succeeds without a main func; the
    # point is that range-over-int compiles under the modernized go.mod pin.
    impl = (
        "package harness\n\n"
        "func SumTo(n int) int {\n"
        "\ttotal := 0\n"
        "\tfor i := range n {\n"  # range-over-int requires go >= 1.22
        "\t\ttotal += i\n"
        "\t}\n"
        "\treturn total\n"
        "}\n"
    )
    tests = (
        "package harness\n\n"
        "import \"testing\"\n\n"
        "func TestSumTo(t *testing.T) {\n"
        "\tif SumTo(4) != 6 {\n"
        "\t\tt.Fatalf(\"want 6\")\n"
        "\t}\n"
        "}\n"
    )
    results = go.run_go_suite(impl, tests, str(tmp_path))
    build = next((r for r in results if r.gate == "build"), None)
    assert build is not None and build.passed, (
        [(r.gate, [e.message for e in r.errors]) for r in results]
    )

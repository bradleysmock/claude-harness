"""Unit + integration tests for the _standards.md schema validator (ticket 0006).

The validator ships at ``validators/standards_validator.py`` (a tracked, plugin-
shipped path, invoked via ``${CLAUDE_PLUGIN_ROOT}``). It is a standalone CLI
script, so the module is loaded from its file path via importlib rather than a
normal package import.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "validators" / "standards_validator.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("standards_validator", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sv = _load_module()

DEFAULT = list(sv.DEFAULT_REQUIRED_SECTIONS)

# --- fixtures -----------------------------------------------------------------

POPULATED = """# Engineering Standards

## Language
Python 3.11 with type annotations on public boundaries.

## Test strategy
pytest with behavior coverage; no unittest.
"""

STUBBED_BODIES = """# Engineering Standards

## Language
TODO

## Test strategy
- (e.g.) pytest + pytest-asyncio.
"""

# Mirrors the real /init _standards.md stub after this ticket: the required
# Language / Test strategy sections are present but their bodies are (e.g.) stubs.
INIT_STUB = """# Engineering Standards

Replace each section's bullets with what actually applies to this project.

## Language

- (e.g.) Python 3.12 is the implementation language and runtime.

## Code style

- (e.g.) Python: black + ruff, 100-character lines.

## Test strategy

- (e.g.) Integration tests hit a real Postgres via testcontainers, never SQLite mocks.
- (e.g.) Behavior coverage is enforced; line coverage is not.

## Security

- (e.g.) User input that reaches a subprocess must use an argv list.
"""

# Same required sections, populated with real (non-stub) content.
FILLED_STANDARDS = """# Engineering Standards

## Language
Python 3.12 is the implementation language and runtime.

## Code style
- (e.g.) black + ruff.

## Test strategy
Unit and integration tests via pytest; behavior coverage is enforced.

## Security
- (e.g.) argv lists for subprocess.
"""


def _extract_init_standards_template() -> str:
    """Pull the fenced `_standards.md` template out of commands/init.md verbatim."""
    text = (ROOT / "commands" / "init.md").read_text(encoding="utf-8")
    marker = text.index("`.tickets/_standards.md`")
    fence_start = text.index("```markdown", marker) + len("```markdown")
    fence_end = text.index("```", fence_start)
    return text[fence_start:fence_end].strip("\n") + "\n"


def _write(tmp_path: Path, text: str, name: str = "_standards.md") -> Path:
    target = tmp_path / ".tickets"
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    path.write_text(text, encoding="utf-8")
    return path


# --- FR-1: file existence & containment ---------------------------------------

def test_missing_file_sets_file_error(tmp_path: Path) -> None:
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    err = excinfo.value
    assert err.file_error is not None
    assert "not found" in err.file_error
    assert err.missing_sections == []
    assert err.stub_sections == []


def test_path_outside_root_is_hard_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes project root"):
        sv.validate("/etc/passwd", DEFAULT, root=tmp_path)


def test_relative_escape_outside_root_is_hard_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes project root"):
        sv.validate("../../etc/passwd", DEFAULT, root=tmp_path)


# --- FR-2: section presence ---------------------------------------------------

def test_missing_language_section(tmp_path: Path) -> None:
    text = "## Test strategy\npytest with real coverage.\n"
    _write(tmp_path, text)
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    assert "language" in excinfo.value.missing_sections
    assert "test strategy" not in excinfo.value.missing_sections


def test_all_required_headings_present_passes(tmp_path: Path) -> None:
    _write(tmp_path, POPULATED)
    assert sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path) is None


def test_h3_heading_variant_detected(tmp_path: Path) -> None:
    text = "### language\nPython.\n\n### test strategy\npytest.\n"
    _write(tmp_path, text)
    assert sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path) is None


# --- FR-3: stub detection -----------------------------------------------------

@pytest.mark.parametrize(
    "body",
    ["TODO", "<fill in>", "- (e.g.) Python: black", "PLACEHOLDER", "tbd", "FIXME this"],
)
def test_stub_bodies_flagged(tmp_path: Path, body: str) -> None:
    text = f"## Language\n{body}\n\n## Test strategy\npytest.\n"
    _write(tmp_path, text)
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    stubbed = {s["section"] for s in excinfo.value.stub_sections}
    assert "language" in stubbed
    assert "test strategy" not in stubbed


def test_mixed_valid_and_stub_line_passes(tmp_path: Path) -> None:
    # "Mixed" means a body with at least one genuine content line alongside stub
    # lines. Under the canonical predicate (fail iff *every* non-blank line is a
    # stub line), one real line makes the section pass — even when stub lines,
    # including a line that itself contains "TODO", sit beside it.
    text = (
        "## Language\n"
        "Python 3.11 with type annotations on public boundaries.\n"
        "- (e.g.) placeholder bullet from the stub\n"
        "TODO: expand this later\n"
        "\n"
        "## Test strategy\npytest.\n"
    )
    _write(tmp_path, text)
    assert sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path) is None


def test_whitespace_only_body_is_stub(tmp_path: Path) -> None:
    text = "## Language\n   \n\t\n\n## Test strategy\npytest.\n"
    _write(tmp_path, text)
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    assert {s["section"] for s in excinfo.value.stub_sections} == {"language"}


def test_empty_body_at_eof_is_stub(tmp_path: Path) -> None:
    text = "## Test strategy\npytest.\n\n## Language\n"
    _write(tmp_path, text)
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    assert "language" in {s["section"] for s in excinfo.value.stub_sections}


@pytest.mark.parametrize("body", ["  Python  ", "Go", "Rust 1.75"])
def test_short_valid_content_passes(tmp_path: Path, body: str) -> None:
    text = f"## Language\n{body}\n\n## Test strategy\npytest.\n"
    _write(tmp_path, text)
    assert sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path) is None


# --- FR-4 / FR-6: CLI contract ------------------------------------------------

def test_main_exit_1_on_stub_no_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, STUBBED_BODIES)
    monkeypatch.chdir(tmp_path)
    rc = sv.main([".tickets/_standards.md"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "validation failed" in captured.err


def test_main_exit_0_silent_on_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, POPULATED)
    monkeypatch.chdir(tmp_path)
    rc = sv.main([".tickets/_standards.md"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""
    assert captured.err == ""


def test_main_misuse_returns_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert sv.main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_init_stub_fails_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, INIT_STUB)
    monkeypatch.chdir(tmp_path)
    assert sv.main([".tickets/_standards.md"]) == 1


# --- FR-5: per-section error message ------------------------------------------

def test_report_enumerates_both_failing_sections(tmp_path: Path) -> None:
    text = "## Language\nTODO\n"  # test strategy missing, language stubbed
    _write(tmp_path, text)
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    report = sv._format_report(excinfo.value)
    assert "test strategy" in report and "missing" in report
    assert "language" in report and "stub content" in report


# --- FR-6 / NFR-2: no side effects on success ---------------------------------

def test_passing_run_has_no_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, POPULATED)
    before = {p for p in tmp_path.rglob("*")}
    sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    after = {p for p in tmp_path.rglob("*")}
    captured = capsys.readouterr()
    assert before == after
    assert captured.out == "" and captured.err == ""


# --- FR-7: configurable section list ------------------------------------------

def test_config_extends_required_sections(tmp_path: Path) -> None:
    _write(tmp_path, POPULATED)  # has language + test strategy, but no security
    with pytest.raises(sv.StandardsValidationError) as excinfo:
        sv.validate(
            ".tickets/_standards.md",
            ["language", "test strategy", "security"],
            root=tmp_path,
        )
    assert "security" in excinfo.value.missing_sections


def test_config_absent_uses_default(tmp_path: Path) -> None:
    missing = tmp_path / "nope.toml"
    assert sv.load_required_sections(missing) == DEFAULT


def test_config_present_overrides_default(tmp_path: Path) -> None:
    cfg = tmp_path / "standards_config.toml"
    cfg.write_text('required_sections = ["language", "security"]\n', encoding="utf-8")
    assert sv.load_required_sections(cfg) == ["language", "security"]


def test_config_malformed_falls_back_to_default(tmp_path: Path) -> None:
    cfg = tmp_path / "standards_config.toml"
    cfg.write_text("required_sections = []\n", encoding="utf-8")
    assert sv.load_required_sections(cfg) == DEFAULT


# --- NFR-1: latency -----------------------------------------------------------

def test_latency_under_50ms(tmp_path: Path) -> None:
    body = "Python 3.11 with type annotations everywhere. " * 20  # ~1 KB section
    text = f"## Language\n{body}\n\n## Test strategy\npytest behavior coverage.\n"
    _write(tmp_path, text)
    start = time.perf_counter()
    sv.validate(".tickets/_standards.md", DEFAULT, root=tmp_path)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05


# --- C-01: end-to-end against the actual /init template -----------------------

def test_real_init_template_unfilled_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The verbatim /init stub (all (e.g.) bullets) must halt — its required
    # Language / Test strategy sections exist but are stubbed.
    _write(tmp_path, _extract_init_standards_template())
    monkeypatch.chdir(tmp_path)
    assert sv.main([".tickets/_standards.md"]) == 1


def test_real_init_template_exposes_required_sections() -> None:
    # Guards the C-01 fix: the shipped stub actually contains the two headings
    # the default validator requires (so a filled stub can pass).
    template = _extract_init_standards_template().lower()
    assert "## language" in template
    assert "## test strategy" in template


def test_filled_standards_with_required_sections_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, FILLED_STANDARDS)
    monkeypatch.chdir(tmp_path)
    assert sv.main([".tickets/_standards.md"]) == 0


# --- C-03: main() halts cleanly on non-validation errors ----------------------

def test_main_containment_error_returns_1_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = sv.main(["/etc/passwd"])  # absolute path outside cwd → containment ValueError
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "could not run" in captured.err  # clean diagnostic, not a traceback


# --- C-06 / C-09: config parse robustness -------------------------------------

def test_config_syntax_error_falls_back_to_default(tmp_path: Path) -> None:
    cfg = tmp_path / "standards_config.toml"
    cfg.write_text("required_sections = [unclosed\n", encoding="utf-8")  # invalid TOML
    assert sv.load_required_sections(cfg) == DEFAULT


def test_config_entries_are_stripped(tmp_path: Path) -> None:
    cfg = tmp_path / "standards_config.toml"
    cfg.write_text(
        'required_sections = ["  language  ", " test strategy "]\n', encoding="utf-8"
    )
    assert sv.load_required_sections(cfg) == ["language", "test strategy"]


def test_config_non_utf8_falls_back_to_default(tmp_path: Path) -> None:
    cfg = tmp_path / "standards_config.toml"
    cfg.write_bytes(b'required_sections = ["\xff\xfelanguage"]\n')  # invalid UTF-8
    assert sv.load_required_sections(cfg) == DEFAULT

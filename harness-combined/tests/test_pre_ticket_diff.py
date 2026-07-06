# harness-combined/tests/test_pre_ticket_diff.py
"""Unit + integration coverage for the pre_ticket_diff PreToolUse hook and the
behaviour-preserving pre_write_guard refactor that shares _common.extract_file_path.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).parent.parent / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass on py3.14 resolves cls.__module__ via
    # sys.modules during class creation.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


diff = _load("pre_ticket_diff")
guard = _load("pre_write_guard")
# Both hooks import _common at load time; bind to that same instance rather than
# loading a second copy, so the delegation identity check below is meaningful.
common = sys.modules["_common"]


# --- test helpers ----------------------------------------------------------

def _ticket_file(tmp_path: Path, monkeypatch, body: str = "line1\nline2\n") -> Path:
    """Create tmp_path/.tickets/0001-x/solution.md and chdir into tmp_path."""
    tdir = tmp_path / ".tickets" / "0001-x"
    tdir.mkdir(parents=True)
    target = tdir / "solution.md"
    target.write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return target


def _run_main(monkeypatch, capsys, payload: dict) -> tuple[int, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = diff.main()
    return rc, capsys.readouterr().err


# --- _common.extract_file_path --------------------------------------------

@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_extract_file_path_returns_path_for_write_tools(tool: str) -> None:
    assert common.extract_file_path(tool, {"file_path": "/x/a.md"}) == "/x/a.md"


def test_extract_file_path_none_for_other_tools() -> None:
    assert common.extract_file_path("Read", {"file_path": "/x/a.md"}) is None


def test_extract_file_path_none_when_missing() -> None:
    assert common.extract_file_path("Write", {}) is None


# --- compute_diff (FR-1, FR-5, FR-6) --------------------------------------

def test_compute_diff_nonempty_with_markers() -> None:
    out = diff.compute_diff("line1\nline2\n", "line1\nCHANGED\n", "solution.md")
    assert out
    assert "---" in out and "+++" in out and "@@" in out


def test_compute_diff_empty_when_identical() -> None:
    assert diff.compute_diff("same\n", "same\n", "solution.md") == ""


def test_compute_diff_line_prefixes() -> None:
    out = diff.compute_diff("line1\nline2\n", "line1\nCHANGED\n", "solution.md")
    assert "-line2" in out
    assert "+CHANGED" in out


# --- should_show_diff (FR-4, FR-5, NFR-2) ---------------------------------

def test_should_show_diff_false_when_missing(tmp_path: Path, monkeypatch) -> None:
    _ticket_file(tmp_path, monkeypatch)
    absent = tmp_path / ".tickets" / "0001-x" / "does-not-exist.md"
    assert diff.should_show_diff(str(absent)) is False


def test_should_show_diff_false_when_empty(tmp_path: Path, monkeypatch) -> None:
    target = _ticket_file(tmp_path, monkeypatch, body="")
    assert diff.should_show_diff(str(target)) is False


def test_should_show_diff_true_for_existing_nonempty_ticket(tmp_path: Path, monkeypatch) -> None:
    target = _ticket_file(tmp_path, monkeypatch)
    assert diff.should_show_diff(str(target)) is True


# --- containment (FR-1) ----------------------------------------------------

def test_path_outside_tickets_absolute_skipped(tmp_path: Path, monkeypatch) -> None:
    _ticket_file(tmp_path, monkeypatch)
    outside = tmp_path / "outside.md"
    outside.write_text("data\n", encoding="utf-8")
    assert diff.is_ticket_artifact(str(outside)) is False
    assert diff.should_show_diff(str(outside)) is False


def test_path_traversal_out_of_tickets_skipped(tmp_path: Path, monkeypatch) -> None:
    _ticket_file(tmp_path, monkeypatch)
    (tmp_path / "secret.md").write_text("secret\n", encoding="utf-8")
    traversal = str(tmp_path / ".tickets" / "0001-x" / ".." / ".." / "secret.md")
    assert diff.is_ticket_artifact(traversal) is False


def test_non_md_under_tickets_skipped(tmp_path: Path, monkeypatch) -> None:
    _ticket_file(tmp_path, monkeypatch)
    active = tmp_path / ".tickets" / ".active"
    active.write_text("0001-x\n", encoding="utf-8")
    assert diff.is_ticket_artifact(str(active)) is False


# --- apply_patches / reconstruct ------------------------------------------

def test_apply_patches_replaces_first_occurrence() -> None:
    assert diff.apply_patches("a b a", [{"old_string": "a", "new_string": "X"}]) == "X b a"


def test_apply_patches_returns_none_when_not_found() -> None:
    assert diff.apply_patches("abc", [{"old_string": "zzz", "new_string": "X"}]) is None


def test_apply_patches_returns_none_on_empty_old() -> None:
    assert diff.apply_patches("abc", [{"old_string": "", "new_string": "X"}]) is None


def test_reconstruct_write_uses_content() -> None:
    assert diff.reconstruct_proposed_content("Write", {"content": "new"}, "old") == "new"


def test_reconstruct_edit_applies_patch() -> None:
    got = diff.reconstruct_proposed_content(
        "Edit", {"old_string": "line2", "new_string": "CHANGED"}, "line1\nline2\n"
    )
    assert got == "line1\nCHANGED\n"


def test_reconstruct_multiedit_applies_sequentially() -> None:
    got = diff.reconstruct_proposed_content(
        "MultiEdit",
        {"edits": [{"old_string": "a", "new_string": "1"}, {"old_string": "b", "new_string": "2"}]},
        "a b",
    )
    assert got == "1 2"


# --- main() dispatch: HARNESS_NO_DIFF (FR-7) ------------------------------

def test_harness_no_diff_suppresses_output(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _ticket_file(tmp_path, monkeypatch)
    monkeypatch.setenv("HARNESS_NO_DIFF", "1")
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "line1\nDIFFERENT\n"},
    })
    assert rc == 0
    assert err == ""


# --- main() dispatch: NFR-2 graceful degradation --------------------------

def test_unreadable_file_exits_zero_no_output(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _ticket_file(tmp_path, monkeypatch)

    def _boom(self, *a, **k):
        raise PermissionError("nope")

    monkeypatch.setattr(Path, "read_text", _boom)
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "x\n"},
    })
    assert rc == 0
    assert err == ""


def test_non_utf8_file_exits_zero_no_output(tmp_path: Path, monkeypatch, capsys) -> None:
    # UnicodeDecodeError (a ValueError, not an OSError) on a non-UTF-8 existing
    # file must still degrade to a silent exit-0, per NFR-2 (regression for M1).
    tdir = tmp_path / ".tickets" / "0001-x"
    tdir.mkdir(parents=True)
    target = tdir / "solution.md"
    target.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    monkeypatch.chdir(tmp_path)
    assert diff.should_show_diff(str(target)) is False
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "clean\n"},
    })
    assert rc == 0
    assert err == ""


def test_plugin_root_env_unset_is_harmless(tmp_path: Path, monkeypatch, capsys) -> None:
    # The hook does not depend on CLAUDE_PLUGIN_ROOT; unsetting or pointing it at
    # a non-existent path must not affect the exit-0 / no-crash contract.
    _ticket_file(tmp_path, monkeypatch)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "elsewhere.md"), "content": "x\n"},
    })
    assert rc == 0
    assert err == ""


def test_malformed_stdin_exits_zero(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert diff.main() == 0
    assert capsys.readouterr().err == ""


# --- main() integration (FR-2) --------------------------------------------

def test_write_to_ticket_emits_diff(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _ticket_file(tmp_path, monkeypatch)
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "line1\nDIFFERENT\n"},
    })
    assert rc == 0
    assert "@@" in err
    assert "-line2" in err and "+DIFFERENT" in err


def test_write_when_file_absent_no_output(tmp_path: Path, monkeypatch, capsys) -> None:
    _ticket_file(tmp_path, monkeypatch)
    new_target = tmp_path / ".tickets" / "0001-x" / "brand-new.md"
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(new_target), "content": "hello\n"},
    })
    assert rc == 0
    assert err == ""


def test_write_identical_content_no_output(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _ticket_file(tmp_path, monkeypatch, body="same\n")
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "same\n"},
    })
    assert rc == 0
    assert err == ""


def test_edit_to_ticket_emits_net_diff(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _ticket_file(tmp_path, monkeypatch, body="alpha\nbeta\ngamma\n")
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(target), "old_string": "beta", "new_string": "BETA"},
    })
    assert rc == 0
    assert "-beta" in err and "+BETA" in err
    # Net diff: only the beta line changed. Unchanged context lines must not
    # carry +/- prefixes.
    assert "+alpha" not in err and "-alpha" not in err
    assert "+gamma" not in err and "-gamma" not in err


def test_multiedit_unmatched_old_string_no_output(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _ticket_file(tmp_path, monkeypatch, body="alpha\nbeta\n")
    rc, err = _run_main(monkeypatch, capsys, {
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": str(target), "edits": [{"old_string": "NOPE", "new_string": "X"}]},
    })
    assert rc == 0
    assert err == ""


# --- pre_write_guard behaviour-preserving refactor ------------------------

def test_guard_uses_shared_extract_file_path() -> None:
    # The guard must delegate to _common.extract_file_path (identity check).
    assert guard.extract_file_path is common.extract_file_path


def test_guard_extract_proposed_content_write() -> None:
    assert guard.extract_proposed_content("Write", {"file_path": "/x/a.py", "content": "x=1"}) == (
        "/x/a.py",
        "x=1",
    )


def test_guard_extract_proposed_content_edit() -> None:
    assert guard.extract_proposed_content("Edit", {"file_path": "/x/a.py", "new_string": "y=2"}) == (
        "/x/a.py",
        "y=2",
    )


def test_guard_extract_proposed_content_multiedit_joins() -> None:
    got = guard.extract_proposed_content(
        "MultiEdit",
        {"file_path": "/x/a.py", "edits": [{"new_string": "a"}, {"new_string": "b"}]},
    )
    assert got == ("/x/a.py", "a\nb")


def test_guard_extract_proposed_content_unknown_tool_is_none() -> None:
    assert guard.extract_proposed_content("Read", {"file_path": "/x/a.py"}) is None


def test_guard_still_blocks_secret(monkeypatch) -> None:
    fake_key = "AKIA" + "A" * 16  # built at runtime so this test file itself is clean
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x/a.py", "content": f"k = '{fake_key}'"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert guard.main() == 2


def test_guard_passes_clean_content(monkeypatch) -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/x/a.py", "content": "x = 1\n"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert guard.main() == 0

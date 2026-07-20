"""Tests for gates.incremental_scope (ticket 0067)."""

from __future__ import annotations

from pathlib import Path

from gates.finding import Finding
from gates.incremental_scope import format_incremental_brief, touched_files_from_diff


def _f(**overrides: object) -> Finding:
    base = dict(file="src/module.py", line=12, severity="BLOCKER", code="Security / Injection", message="body")
    base.update(overrides)
    return Finding(**base)


MODIFY_DIFF = """\
diff --git a/src/a.py b/src/a.py
index 1111111..2222222 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,1 +1,1 @@
-old
+new
diff --git a/src/b.py b/src/b.py
index 3333333..4444444 100644
--- a/src/b.py
+++ b/src/b.py
@@ -1,1 +1,1 @@
-old
+new
"""

RENAME_DIFF = """\
diff --git a/a.py b/b.py
similarity index 100%
rename from a.py
rename to b.py
"""

BINARY_DIFF = """\
diff --git a/img.png b/img.png
index 5555555..6666666 100644
Binary files a/img.png and b/img.png differ
"""

DELETE_DIFF = """\
diff --git a/src/gone.py b/src/gone.py
deleted file mode 100644
index 7777777..0000000
--- a/src/gone.py
+++ /dev/null
@@ -1,1 +0,0 @@
-content
"""


def test_touched_files_from_diff_returns_both_modified_files_sorted_deduped(tmp_path: Path) -> None:
    result = touched_files_from_diff(MODIFY_DIFF, tmp_path)
    assert result == ["src/a.py", "src/b.py"]


def test_touched_files_from_diff_rename_returns_both_old_and_new(tmp_path: Path) -> None:
    result = touched_files_from_diff(RENAME_DIFF, tmp_path)
    assert result == ["a.py", "b.py"]


def test_touched_files_from_diff_binary_returns_named_paths_without_hunk(tmp_path: Path) -> None:
    result = touched_files_from_diff(BINARY_DIFF, tmp_path)
    assert result == ["img.png"]


def test_touched_files_from_diff_delete_returns_old_side_only(tmp_path: Path) -> None:
    result = touched_files_from_diff(DELETE_DIFF, tmp_path)
    assert result == ["src/gone.py"]


def test_touched_files_from_diff_drops_path_escaping_worktree_root(tmp_path: Path) -> None:
    escaping = """\
diff --git a/../../etc/passwd b/../../etc/passwd
--- a/../../etc/passwd
+++ b/../../etc/passwd
@@ -1,1 +1,1 @@
-old
+new
"""
    result = touched_files_from_diff(escaping, tmp_path)
    assert result == []


def test_touched_files_from_diff_empty_text_returns_empty_list(tmp_path: Path) -> None:
    assert touched_files_from_diff("", tmp_path) == []


def test_touched_files_from_diff_malformed_text_returns_empty_list_without_raising(tmp_path: Path) -> None:
    assert touched_files_from_diff("not a diff at all\njust prose\n", tmp_path) == []


def test_touched_files_from_diff_never_raises_on_none_like_input(tmp_path: Path) -> None:
    assert touched_files_from_diff(None, tmp_path) == []  # type: ignore[arg-type]


def test_format_incremental_brief_embeds_finding_and_diff() -> None:
    f = _f(file="src/a.py", line=12, message="Fix the thing.")
    brief = format_incremental_brief([f], MODIFY_DIFF)
    assert "Mode: incremental" in brief
    assert "src/a.py:12" in brief
    assert "Fix the thing." in brief
    assert MODIFY_DIFF in brief


def test_format_incremental_brief_handles_empty_findings_and_diff() -> None:
    brief = format_incremental_brief([], "")
    assert brief
    assert "No prior BLOCKER/MAJOR findings carried forward." in brief
    assert "No diff captured for this round." in brief


def test_format_incremental_brief_is_deterministic() -> None:
    f = _f()
    first = format_incremental_brief([f], MODIFY_DIFF)
    second = format_incremental_brief([f], MODIFY_DIFF)
    assert first == second


def test_format_incremental_brief_preserves_prior_findings_order() -> None:
    a = _f(file="src/a.py", line=1, message="first")
    b = _f(file="src/b.py", line=2, message="second")
    brief = format_incremental_brief([a, b], MODIFY_DIFF)
    assert brief.index("first") < brief.index("second")

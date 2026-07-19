"""Tests for inline PR comment posting (ticket 0031).

All ``gh`` interaction is mocked — unit tests patch ``subprocess.run`` (or the
``detect_pr`` / ``fetch_existing_hashes`` seams) so nothing here needs a live ``gh``
binary, network, or authenticated session.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from gates import comment_deduplicator, pr_commenter, pr_detector
from gates.comment_deduplicator import (
    critic_hash,
    fetch_existing_hashes,
    gate_hash,
    hash_for,
    marker_for,
)
from gates.critic_finding_parser import parse_critic_findings
from gates.finding import (
    PR,
    DeduplicationFailed,
    Finding,
    GhUnavailable,
    NoPRFound,
    NotAuthenticated,
    PostResult,
    validate_finding,
)
from gates.finding_parser import parse_gate_findings
from gates.pr_commenter import format_summary, post_findings

VALID_OID = "a" * 40  # a well-formed 40-char lowercase-hex SHA-1


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# --------------------------------------------------------------------------- #
# gates/finding.py — Finding + validate_finding
# --------------------------------------------------------------------------- #

def test_finding_is_frozen_hashable() -> None:
    f = Finding(file="a.py", line=1, severity="BLOCKER", code="X", message="m")
    assert hash(f) is not None
    with pytest.raises(Exception):
        f.line = 2  # type: ignore[misc]


def test_validate_finding_inside_worktree(tmp_path: Path) -> None:
    f = Finding(file="gates/x.py", line=3, severity="MAJOR", code="", message="m")
    assert validate_finding(f, tmp_path.resolve()) is True


def test_validate_finding_escapes_worktree(tmp_path: Path) -> None:
    f = Finding(file="../etc/passwd", line=1, severity="MAJOR", code="", message="m")
    assert validate_finding(f, tmp_path.resolve()) is False


@pytest.mark.parametrize("line,expected", [(0, False), (-1, False), (None, True), (5, True)])
def test_validate_finding_line_bounds(tmp_path: Path, line: int | None, expected: bool) -> None:
    f = Finding(file="a.py", line=line, severity="MAJOR", code="", message="m")
    assert validate_finding(f, tmp_path.resolve()) is expected


def test_validate_finding_empty_severity(tmp_path: Path) -> None:
    f = Finding(file="a.py", line=1, severity="", code="", message="m")
    assert validate_finding(f, tmp_path.resolve()) is False


def test_result_types_are_distinct() -> None:
    assert type(NoPRFound()) is not type(GhUnavailable("x"))
    assert PostResult(posted=3, skipped=1).posted == 3
    assert PostResult(posted=3, skipped=1).skipped == 1
    assert PR(1, "b", "deadbeef").number == 1


# --------------------------------------------------------------------------- #
# gates/finding_parser.py — parse_gate_findings (FR-2)
# --------------------------------------------------------------------------- #

def test_parse_gate_well_formed(tmp_path: Path) -> None:
    p = tmp_path / "gate-findings.md"
    p.write_text("- `gates/x.py:12` [`E501`]: line too long\n")
    findings = parse_gate_findings(p, tmp_path)
    assert len(findings) == 1
    assert findings[0].file == "gates/x.py"
    assert findings[0].line == 12
    assert findings[0].code == "E501"


def test_parse_gate_non_integer_line_skipped(tmp_path: Path) -> None:
    p = tmp_path / "gate-findings.md"
    p.write_text("- `gates/x.py:notanumber` [`E1`]: bad\n")
    assert parse_gate_findings(p, tmp_path) == []


def test_parse_gate_file_outside_worktree_skipped(tmp_path: Path) -> None:
    p = tmp_path / "gate-findings.md"
    p.write_text("- `../evil.py:1` [`E1`]: escape\n")
    assert parse_gate_findings(p, tmp_path) == []


def test_parse_gate_optional_code_absent(tmp_path: Path) -> None:
    p = tmp_path / "gate-findings.md"
    p.write_text("- `gates/x.py:7`: no code here\n")
    findings = parse_gate_findings(p, tmp_path)
    assert len(findings) == 1
    assert findings[0].code == ""


def test_parse_gate_missing_file_returns_empty(tmp_path: Path) -> None:
    assert parse_gate_findings(tmp_path / "nope.md", tmp_path) == []


# --------------------------------------------------------------------------- #
# gates/critic_finding_parser.py — parse_critic_findings (FR-2)
# --------------------------------------------------------------------------- #

def test_parse_critic_blocker_with_fileline(tmp_path: Path) -> None:
    text = "**BLOCKER** · Security / Auth · `gates/x.py:10`\n\nMissing check.\n"
    findings = parse_critic_findings(text, tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == "BLOCKER"
    assert findings[0].file == "gates/x.py"
    assert findings[0].line == 10
    assert "Missing check." in findings[0].message


def test_parse_critic_minor_without_fileline(tmp_path: Path) -> None:
    text = "**MINOR** · Style / Naming · consider renaming\n\nThe helper name is vague.\n"
    findings = parse_critic_findings(text, tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == "MINOR"
    assert findings[0].file == ""
    assert findings[0].line is None


def test_parse_critic_mid_sentence_fileline(tmp_path: Path) -> None:
    text = "**MAJOR** · Perf / IO · the loop in `gates/y.py:5` reopens the file\n\nHoist it.\n"
    findings = parse_critic_findings(text, tmp_path)
    assert findings[0].file == "gates/y.py"
    assert findings[0].line == 5


def test_parse_critic_three_mixed(tmp_path: Path) -> None:
    text = (
        "**BLOCKER** · A / B · `a.py:1`\n\nfirst\n\n"
        "**MAJOR** · C / D · `b.py:2`\n\nsecond\n\n"
        "**MINOR** · E / F · no location\n\nthird\n"
    )
    findings = parse_critic_findings(text, tmp_path)
    assert [f.severity for f in findings] == ["BLOCKER", "MAJOR", "MINOR"]
    assert findings[2].file == ""


def test_parse_critic_finding_table_all_severities(tmp_path: Path) -> None:
    # The critique skill's CRITIQUE.md keeps MINOR/OBS only in the Finding Table.
    text = (
        "## Finding Table\n\n"
        "| ID | Severity | Panel | Dimension | Location | Finding |\n"
        "|----|----------|-------|-----------|----------|---------|\n"
        "| C-01 | BLOCKER | Sec | Auth | `a.py:10` | missing check |\n"
        "| C-02 | MINOR | Style | Naming | `b.py:2` | vague name |\n"
        "| C-03 | OBS | Core | Tradeoff | — | a note with no location |\n\n"
        "## BLOCKER & MAJOR Detail\n\n"
        "### C-01: X\n**BLOCKER** · Sec · Auth · `a.py:10`\n\nbody\n"
    )
    findings = parse_critic_findings(text, tmp_path)
    # Table is authoritative when present — 3 rows, not the detail block re-counted.
    assert [f.severity for f in findings] == ["BLOCKER", "MINOR", "OBS"]
    assert findings[0].file == "a.py" and findings[0].line == 10
    assert findings[1].severity == "MINOR" and findings[1].file == "b.py"
    assert findings[2].file == "" and findings[2].line is None  # no location -> top-level


def test_critic_same_anchor_different_panel_distinct_hash(tmp_path: Path) -> None:
    # Two distinct findings on the same line+severity must NOT collide in dedup.
    text = (
        "## Finding Table\n\n"
        "| ID | Severity | Panel | Dimension | Location | Finding |\n"
        "|----|----------|-------|-----------|----------|---------|\n"
        "| C-01 | MAJOR | Security | Auth | `a.py:10` | secret leak |\n"
        "| C-02 | MAJOR | Performance | IO | `a.py:10` | N+1 query |\n"
    )
    findings = parse_critic_findings(text, tmp_path)
    assert len(findings) == 2
    assert findings[0].code != findings[1].code
    assert critic_hash(findings[0]) != critic_hash(findings[1])


def test_critic_header_block_captures_panel_code(tmp_path: Path) -> None:
    a = "**MAJOR** · Security / Auth · `a.py:10`\n\nfirst\n"
    b = "**MAJOR** · Performance / IO · `a.py:10`\n\nsecond\n"
    fa = parse_critic_findings(a, tmp_path)[0]
    fb = parse_critic_findings(b, tmp_path)[0]
    assert fa.code and fb.code and fa.code != fb.code
    assert critic_hash(fa) != critic_hash(fb)


# --------------------------------------------------------------------------- #
# gates/pr_detector.py — detect_pr (FR-1)
# --------------------------------------------------------------------------- #

def test_detect_pr_gh_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise FileNotFoundError()
    monkeypatch.setattr(pr_detector.subprocess, "run", boom)
    assert isinstance(pr_detector.detect_pr(), GhUnavailable)


def test_detect_pr_not_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr_detector.subprocess, "run", lambda *a, **k: _proc(1))
    assert isinstance(pr_detector.detect_pr(), NotAuthenticated)


def test_detect_pr_no_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake(*a: object, **k: object) -> types.SimpleNamespace:
        calls["n"] += 1
        return _proc(0) if calls["n"] == 1 else _proc(1)  # auth ok, pr view fails

    monkeypatch.setattr(pr_detector.subprocess, "run", fake)
    assert isinstance(pr_detector.detect_pr(), NoPRFound)


def test_detect_pr_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake(*a: object, **k: object) -> types.SimpleNamespace:
        calls["n"] += 1
        if calls["n"] == 1:
            return _proc(0)
        return _proc(0, stdout='{"number": 42, "headRefName": "feat", "headRefOid": "abc123"}')

    monkeypatch.setattr(pr_detector.subprocess, "run", fake)
    pr = pr_detector.detect_pr()
    assert isinstance(pr, PR)
    assert pr.number == 42 and pr.head_ref == "feat" and pr.head_oid == "abc123"


def test_commentable_lines_basic() -> None:
    patch = "@@ -1,2 +1,3 @@\n ctx\n-old\n+add1\n+add2"
    # new file: ctx=1 (context), add1=2, add2=3.
    assert pr_detector._commentable_lines(patch) == {1, 2, 3}


def test_commentable_lines_ignores_no_newline_marker() -> None:
    patch = "@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n\\ No newline at end of file"
    # The "\ No newline" marker must neither count as a line nor advance the counter.
    assert pr_detector._commentable_lines(patch) == {1, 2}


def test_detect_pr_uses_argument_list(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    def fake(args: object, *a: object, **k: object) -> types.SimpleNamespace:
        seen.append(args)
        return _proc(1)  # stop after auth

    monkeypatch.setattr(pr_detector.subprocess, "run", fake)
    pr_detector.detect_pr()
    assert isinstance(seen[0], list)  # argv list, never a shell string


# --------------------------------------------------------------------------- #
# gates/comment_deduplicator.py — hashing + fetch (FR-5)
# --------------------------------------------------------------------------- #

def test_gate_hash_stable() -> None:
    f = Finding(file="a.py", line=1, severity="MAJOR", code="", message="msg")
    assert gate_hash(f) == gate_hash(f)


def test_critic_hash_ignores_message() -> None:
    a = Finding(file="a.py", line=1, severity="BLOCKER", code="C1", message="first phrasing")
    b = Finding(file="a.py", line=1, severity="BLOCKER", code="C1", message="totally different")
    assert critic_hash(a) == critic_hash(b)


def _fetch_fake(pulls: list[dict] | None = None, issues: list[dict] | None = None):
    """Fake ``subprocess.run`` returning distinct payloads per gh api endpoint."""
    def fake(args: list, *a: object, **k: object) -> types.SimpleNamespace:
        path = args[2]
        data = issues if "issues" in path else pulls
        return _proc(0, stdout=json.dumps(data or []))
    return fake


def test_fetch_harvests_markers_from_both_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    f1 = Finding("a.py", 1, "MAJOR", "", "one")
    f2 = Finding("b.py", 2, "MAJOR", "", "two")
    pulls = [{"path": "a.py", "line": 1, "body": f"x {marker_for(f1, 'gate')}"}]
    issues = [{"body": f"y {marker_for(f2, 'gate')}"}]
    monkeypatch.setattr(comment_deduplicator.subprocess, "run", _fetch_fake(pulls, issues))
    result = fetch_existing_hashes(1, "{owner}/{repo}", "gate")
    assert result == {hash_for(f1, "gate"), hash_for(f2, "gate")}


def test_gate_dedup_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    # The body the commenter *writes* must be readable back into the same hash.
    f = Finding("a.py", 1, "MAJOR", "", "msg")
    pulls = [{"path": "a.py", "line": 1, "body": pr_commenter._inline_body(f, "gate")}]
    monkeypatch.setattr(comment_deduplicator.subprocess, "run", _fetch_fake(pulls=pulls))
    assert hash_for(f, "gate") in fetch_existing_hashes(1, "{owner}/{repo}", "gate")


def test_critic_toplevel_dedup_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    # A top-level critic finding (no file:line) must still dedup across re-runs.
    f = Finding("", None, "MINOR", "", "a top-level nit")
    issues = [{"body": pr_commenter._render_toplevel_body([f], "critic")}]
    monkeypatch.setattr(comment_deduplicator.subprocess, "run", _fetch_fake(issues=issues))
    assert hash_for(f, "critic") in fetch_existing_hashes(1, "{owner}/{repo}", "critic")


def test_fetch_existing_non_zero_is_dedup_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comment_deduplicator.subprocess, "run", lambda *a, **k: _proc(1))
    assert isinstance(fetch_existing_hashes(1, "{owner}/{repo}", "gate"), DeduplicationFailed)


def test_fetch_existing_bad_json_is_dedup_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comment_deduplicator.subprocess, "run", lambda *a, **k: _proc(0, stdout="not json"))
    assert isinstance(fetch_existing_hashes(1, "{owner}/{repo}", "gate"), DeduplicationFailed)


# --------------------------------------------------------------------------- #
# gates/pr_commenter.py — post_findings orchestrator
# --------------------------------------------------------------------------- #

def _patch_pr(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    monkeypatch.setattr(pr_detector, "detect_pr", lambda cwd=None: result)


def _patch_diff(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, set[int]] | None) -> None:
    """Patch the diff-line fetch so tests never touch a real ``gh``."""
    monkeypatch.setattr(pr_detector, "fetch_diff_lines", lambda pr, repo, cwd=None: mapping)


class _Capture:
    """Capture review payload and issue-comment body without hitting ``gh``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, review_result: str = "ok") -> None:
        self.review: dict[str, object] = {}
        self.issue_body: str | None = None
        monkeypatch.setattr(pr_commenter, "_submit_review", self._review(review_result))
        monkeypatch.setattr(pr_commenter, "_submit_issue_comment", self._issue())

    def _review(self, result: str):
        def fn(payload: dict, cwd: object) -> str:
            self.review = payload
            return result
        return fn

    def _issue(self):
        def fn(body: str, pr_number: int, cwd: object) -> bool:
            self.issue_body = body
            return True
        return fn


def _no_gh(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Make any real subprocess call fail the test if it happens."""
    calls: list[object] = []

    def guard(*a: object, **k: object) -> types.SimpleNamespace:
        calls.append(a)
        raise AssertionError("no subprocess call expected")

    monkeypatch.setattr(pr_commenter.subprocess, "run", guard)
    return calls


def test_should_post_false_makes_no_gh_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_gh(monkeypatch)
    # detect_pr must not even be called
    monkeypatch.setattr(pr_detector, "detect_pr", lambda cwd=None: (_ for _ in ()).throw(AssertionError()))
    findings = [Finding("a.py", 1, "MAJOR", "", "m")]
    assert post_findings(findings, tmp_path, should_post=False) == PostResult(0, 0)


def test_no_pr_falls_back_no_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, NoPRFound())
    _no_gh(monkeypatch)
    findings = [Finding("a.py", 1, "MAJOR", "", "m")]
    assert post_findings(findings, tmp_path, should_post=True) == PostResult(0, 0)


def test_gh_unavailable_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _patch_pr(monkeypatch, GhUnavailable("x"))
    with caplog.at_level("WARNING"):
        post_findings([Finding("a.py", 1, "MAJOR", "", "m")], tmp_path, should_post=True)
    assert any("gh not installed" in r.message for r in caplog.records)


def test_not_authenticated_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _patch_pr(monkeypatch, NotAuthenticated("x"))
    with caplog.at_level("WARNING"):
        post_findings([Finding("a.py", 1, "MAJOR", "", "m")], tmp_path, should_post=True)
    assert any("gh not authenticated" in r.message for r in caplog.records)


def test_invalid_sha_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _patch_pr(monkeypatch, PR(1, "feat", "NOT-A-SHA"))
    _no_gh(monkeypatch)
    with caplog.at_level("WARNING"):
        result = post_findings([Finding("a.py", 1, "MAJOR", "", "m")], tmp_path, should_post=True)
    assert result == PostResult(0, 0)
    assert any("Invalid commit SHA" in r.message for r in caplog.records)


def test_dedup_failed_aborts_no_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(1, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: DeduplicationFailed("x"))
    _no_gh(monkeypatch)
    assert post_findings([Finding("a.py", 1, "MAJOR", "", "m")], tmp_path, should_post=True) == PostResult(0, 0)


def test_batch_single_reviews_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, {"a.py": {1, 2, 3}})  # all three lines are in-diff
    calls: list[object] = []

    def fake_run(args: object, *a: object, **k: object) -> types.SimpleNamespace:
        calls.append(args)
        return _proc(0)

    monkeypatch.setattr(pr_commenter.subprocess, "run", fake_run)
    findings = [Finding("a.py", i, "MAJOR", "", f"m{i}") for i in range(1, 4)]
    result = post_findings(findings, tmp_path, should_post=True)
    assert result.posted == 3
    assert len(calls) == 1  # exactly one gh api reviews submission (FR-9)


def test_dedup_skips_matching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    _patch_diff(monkeypatch, None)
    dup = Finding("a.py", 1, "MAJOR", "", "dup")
    fresh = Finding("b.py", 2, "MAJOR", "", "new")
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: {gate_hash(dup)})
    _Capture(monkeypatch)
    result = post_findings([dup, fresh], tmp_path, should_post=True)
    assert result == PostResult(posted=1, skipped=1)


def test_suggestion_prefix_for_minor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, {"a.py": {1}})  # in-diff, so it posts inline
    cap = _Capture(monkeypatch)
    post_findings([Finding("a.py", 1, "MINOR", "", "nit")], tmp_path, should_post=True, kind="critic")
    bodies = [c["body"] for c in cap.review["comments"]]  # type: ignore[union-attr]
    assert bodies[0].startswith("[suggestion] ")


def test_inline_finding_routes_inline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, {"a.py": {3}})
    cap = _Capture(monkeypatch)
    post_findings([Finding("a.py", 3, "MAJOR", "", "inline one")], tmp_path, should_post=True)
    assert len(cap.review["comments"]) == 1
    assert cap.issue_body is None  # nothing routed top-level


def test_no_location_finding_routes_toplevel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, {})
    cap = _Capture(monkeypatch)
    post_findings([Finding("", None, "MAJOR", "", "no location")], tmp_path, should_post=True)
    assert cap.review == {}  # no inline review submitted
    assert cap.issue_body is not None and "no location" in cap.issue_body


def test_offdiff_line_routes_toplevel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-3: a file:line NOT in the diff must fall back to a top-level comment.
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, {"a.py": {1, 2}})  # line 99 is off-diff
    cap = _Capture(monkeypatch)
    result = post_findings([Finding("a.py", 99, "MAJOR", "", "off diff")], tmp_path, should_post=True)
    assert cap.review == {}  # not posted inline
    assert cap.issue_body is not None and "a.py:99" in cap.issue_body
    assert result.posted == 1


def test_offdiff_422_demotes_to_toplevel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-3 best-effort: diff map unavailable, GitHub rejects with off_diff -> demote.
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, None)  # diff unknown -> optimistic inline
    cap = _Capture(monkeypatch, review_result="off_diff")
    result = post_findings([Finding("a.py", 5, "MAJOR", "", "rejected")], tmp_path, should_post=True)
    assert cap.issue_body is not None and "a.py:5" in cap.issue_body
    assert result.posted == 1


def test_body_size_over_limit_takes_summary_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, None)  # optimistic inline
    cap = _Capture(monkeypatch)
    big = "x" * 2000
    findings = [Finding("a.py", i, "MAJOR", "", big) for i in range(1, 51)]
    result = post_findings(findings, tmp_path, should_post=True)
    assert cap.review == {}  # oversized: no inline batch
    assert cap.issue_body is not None and "gate-findings.md" in cap.issue_body
    assert result.posted == 50


def test_body_size_under_limit_takes_inline_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, None)  # optimistic inline
    cap = _Capture(monkeypatch)
    findings = [Finding("a.py", i, "MAJOR", "", "short") for i in range(1, 51)]
    post_findings(findings, tmp_path, should_post=True)
    assert len(cap.review["comments"]) == 50  # inline batch path


def test_dry_run_computes_result_without_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pr(monkeypatch, PR(7, "feat", VALID_OID))
    monkeypatch.setattr(pr_commenter, "fetch_existing_hashes", lambda *a, **k: set())
    _patch_diff(monkeypatch, {"a.py": {1}})
    _no_gh(monkeypatch)
    findings = [Finding("a.py", 1, "MAJOR", "", "m")]
    assert post_findings(findings, tmp_path, should_post=True, dry_run=True) == PostResult(1, 0)


def test_format_summary_contains_counts() -> None:
    s = format_summary(PostResult(posted=3, skipped=1))
    assert "3" in s and "1" in s

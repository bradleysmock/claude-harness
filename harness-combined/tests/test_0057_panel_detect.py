"""Unit tests for panel_detect.py (ticket 0057).

Covers each trigger kind, the JSON/evidence contract, fail-closed data and
invocation faults, skip reasons, and determinism.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "panel_detect.py"

sys.path.insert(0, str(ROOT))
import panel_detect  # noqa: E402


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def active_panels(result: subprocess.CompletedProcess) -> list[str]:
    return [p["panel"] for p in json.loads(result.stdout)["active"]]


# --- per-trigger-kind fixtures -----------------------------------------


def test_glob_trigger_activates_panel(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.go").write_text("package main\n")
    result = run_cli("--root", str(tmp_path), "app/main.go")
    assert result.returncode == 0
    assert "go" in active_panels(result)


def test_manifest_trigger_activates_panel(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n")
    (tmp_path / "README.md").write_text("hello\n")
    result = run_cli("--root", str(tmp_path), "README.md")
    assert result.returncode == 0
    assert "rust" in active_panels(result)


def test_dep_trigger_activates_panel(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["cryptography>=41"]\n'
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "app.py")
    assert result.returncode == 0
    assert "cryptography" in active_panels(result)


def test_dep_trigger_requirements_txt_word_boundary(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# comment\n-e ./local-pkg\n--extra-index-url https://example.com\ncryptography>=41,<42\n"
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "app.py")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    crypto = next(p for p in payload["active"] if p["panel"] == "cryptography")
    matched_patterns = {ev["pattern"] for ev in crypto["evidence"]}
    assert "cryptography" in matched_patterns


def test_requirements_txt_option_lines_not_mistaken_for_deps() -> None:
    text = "-e ./local-pkg\n--extra-index-url https://example.com\n-r other.txt\ncryptography>=41,<42\n"
    names = panel_detect._dep_names_from_manifest("requirements.txt", text)
    assert names == {"cryptography"}


def test_dep_trigger_go_mod_word_boundary(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\ngo 1.21\n\nrequire (\n\tgoogle.golang.org/grpc v1.58.0\n)\n"
    )
    (tmp_path / "main.go").write_text("package main\n")
    result = run_cli("--root", str(tmp_path), "main.go")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    grpc = next(p for p in payload["active"] if p["panel"] == "grpc-protobuf")
    matched_patterns = {ev["pattern"] for ev in grpc["evidence"]}
    assert "google.golang.org/grpc" in matched_patterns


def test_dep_trigger_gemfile_word_boundary(tmp_path: Path) -> None:
    (tmp_path / "Gemfile").write_text("source 'https://rubygems.org'\ngem 'sidekiq'\n")
    (tmp_path / "app.rb").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "app.rb")
    payload = json.loads(result.stdout)
    dist = next(p for p in payload["active"] if p["panel"] == "distributed")
    matched_patterns = {ev["pattern"] for ev in dist["evidence"]}
    assert "sidekiq" in matched_patterns


def test_dep_trigger_nested_in_scope_manifest_consulted(tmp_path: Path) -> None:
    (tmp_path / "services" / "worker").mkdir(parents=True)
    (tmp_path / "services" / "worker" / "package.json").write_text(
        '{"dependencies": {"@angular/core": "^17.0.0"}}\n'
    )
    (tmp_path / "app.js").write_text("export const x = 1;\n")
    result = run_cli(
        "--root", str(tmp_path), "app.js", "services/worker/package.json"
    )
    assert result.returncode == 0
    assert "angular" in active_panels(result)


def test_dep_near_miss_preact_does_not_match_react(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"preact": "^10.0.0"}}\n')
    (tmp_path / "app.js").write_text("export const x = 1;\n")
    result = run_cli("--root", str(tmp_path), "app.js")
    assert result.returncode == 0
    panels = active_panels(result)
    assert "typescript" in panels
    assert "react" not in panels


def test_path_keyword_trigger_activates_panel(tmp_path: Path) -> None:
    (tmp_path / "src" / "handlers").mkdir(parents=True)
    (tmp_path / "src" / "handlers" / "widget.py").write_text("def h(): pass\n")
    result = run_cli("--root", str(tmp_path), "src/handlers/widget.py")
    assert result.returncode == 0
    assert "http-api" in active_panels(result)


def test_content_trigger_activates_panel(tmp_path: Path) -> None:
    (tmp_path / "page.py").write_text('def view(): return "<div hx-get=\\"/x\\"></div>"\n')
    result = run_cli("--root", str(tmp_path), "page.py")
    assert result.returncode == 0
    assert "hypermedia" in active_panels(result)


# --- worked examples (AC) -----------------------------------------------


def test_python_route_handler_worked_example(tmp_path: Path) -> None:
    (tmp_path / "app" / "routes").mkdir(parents=True)
    (tmp_path / "app" / "routes" / "users.py").write_text("def get_users(): return []\n")
    result = run_cli("--root", str(tmp_path), "app/routes/users.py")
    assert result.returncode == 0
    assert active_panels(result) == ["core", "python", "http-api"]


def test_tsx_worked_example(tmp_path: Path) -> None:
    (tmp_path / "Comp.tsx").write_text("export const C = () => <div/>;\n")
    result = run_cli("--root", str(tmp_path), "Comp.tsx")
    assert result.returncode == 0
    assert set(active_panels(result)) == {"core", "typescript", "ui"}


def test_sql_migration_worked_example(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("CREATE TABLE x (id int);\n")
    result = run_cli("--root", str(tmp_path), "migrations/001.sql")
    assert result.returncode == 0
    assert active_panels(result) == ["core", "database"]


# --- JSON / evidence contract -------------------------------------------


def test_core_is_always_first(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi\n")
    result = run_cli("--root", str(tmp_path), "README.md")
    payload = json.loads(result.stdout)
    assert payload["active"][0]["panel"] == "core"


def test_evidence_never_carries_matched_content(tmp_path: Path) -> None:
    (tmp_path / "page.py").write_text('SECRET_PHRASE = "hx-get=/private-instruction"\n')
    result = run_cli("--root", str(tmp_path), "page.py")
    payload = json.loads(result.stdout)
    rendered = json.dumps(payload)
    assert "SECRET_PHRASE" not in rendered
    assert "private-instruction" not in rendered
    hyper = next(p for p in payload["active"] if p["panel"] == "hypermedia")
    for ev in hyper["evidence"]:
        assert set(ev) == {"kind", "path", "pattern"}


def test_determinism_byte_identical_repeat_run(tmp_path: Path) -> None:
    (tmp_path / "app" / "routes").mkdir(parents=True)
    (tmp_path / "app" / "routes" / "users.py").write_text("def get_users(): return []\n")
    first = run_cli("--root", str(tmp_path), "app/routes/users.py")
    second = run_cli("--root", str(tmp_path), "app/routes/users.py")
    assert first.stdout == second.stdout


# --- candidates / judgment ------------------------------------------------


def test_judgment_trigger_never_auto_activates(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "app.py")
    payload = json.loads(result.stdout)
    assert "database" not in active_panels(result)
    candidate = next(c for c in payload["candidates"] if c["panel"] == "database")
    assert candidate["reasons"]


def test_design_mode_root_manifest_activates_deterministically(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    result = run_cli("--root", str(tmp_path), "--design")
    assert result.returncode == 0
    assert "python" in active_panels(result)


def test_design_mode_content_dependent_panel_becomes_candidate(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    result = run_cli("--root", str(tmp_path), "--design")
    payload = json.loads(result.stdout)
    assert "http-api" not in active_panels(result)
    candidate = next(c for c in payload["candidates"] if c["panel"] == "http-api")
    assert any("design mode" in r for r in candidate["reasons"])


# --- fail-closed: trigger-data faults -------------------------------------


def _write_fenced(path: Path, body: str) -> None:
    path.write_text(f"```toml\n{body}\n```\n")


def test_missing_triggers_file_fails_closed(tmp_path: Path) -> None:
    result = run_cli(
        "--root", str(tmp_path), "--triggers", str(tmp_path / "nope.md"), "x.py"
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip()


def test_unparseable_toml_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    _write_fenced(trig, "this is [[[ not toml")
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0
    assert result.stdout == ""


def test_zero_fences_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    trig.write_text("no fence here\n")
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0


def test_multiple_fences_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    trig.write_text('```toml\n[panels.python]\nfile = "python.md"\n```\n```toml\n[panels.go]\nfile = "go.md"\n```\n')
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0


def test_unknown_key_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    _write_fenced(trig, '[panels.python]\nfile = "python.md"\nbogus = ["x"]')
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0


def test_wrong_type_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    _write_fenced(trig, '[panels.python]\nfile = "python.md"\nglobs = "not-a-list"')
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0


def test_catastrophic_content_pattern_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    _write_fenced(trig, "[panels.python]\nfile = \"python.md\"\ncontent = ['(a+)+']")
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0
    assert result.stdout == ""


def test_missing_file_field_fails_closed(tmp_path: Path) -> None:
    trig = tmp_path / "triggers.md"
    _write_fenced(trig, '[panels.python]\nglobs = ["**/*.py"]')
    (tmp_path / "x.py").write_text("x = 1\n")
    result = run_cli("--root", str(tmp_path), "--triggers", str(trig), "x.py")
    assert result.returncode != 0


# --- fail-closed: invalid invocation --------------------------------------


def test_nonexistent_root_fails_closed(tmp_path: Path) -> None:
    result = run_cli("--root", str(tmp_path / "nope"), "x.py")
    assert result.returncode != 0
    assert result.stdout == ""


def test_root_not_a_directory_fails_closed(tmp_path: Path) -> None:
    f = tmp_path / "notadir"
    f.write_text("x\n")
    result = run_cli("--root", str(f), "x.py")
    assert result.returncode != 0


def test_empty_file_list_without_design_fails_closed(tmp_path: Path) -> None:
    result = run_cli("--root", str(tmp_path))
    assert result.returncode != 0
    assert result.stdout == ""


def test_empty_file_list_with_design_succeeds(tmp_path: Path) -> None:
    result = run_cli("--root", str(tmp_path), "--design")
    assert result.returncode == 0


# --- skip reasons (NFR-1) --------------------------------------------------


def test_skip_reason_missing(tmp_path: Path) -> None:
    result = run_cli("--root", str(tmp_path), "does-not-exist.py")
    payload = json.loads(result.stdout)
    assert {"path": "does-not-exist.py", "reason": "missing"} in payload["skipped"]


def test_skip_reason_oversize(tmp_path: Path) -> None:
    big = tmp_path / "big.py"
    big.write_text("x = 1\n" * 200_000)
    result = run_cli("--root", str(tmp_path), "big.py")
    payload = json.loads(result.stdout)
    reasons = {s["reason"] for s in payload["skipped"] if s["path"] == "big.py"}
    assert "oversize" in reasons


def test_skip_reason_binary(tmp_path: Path) -> None:
    binf = tmp_path / "blob.py"
    binf.write_bytes(b"\x00\x01\x02binary")
    result = run_cli("--root", str(tmp_path), "blob.py")
    payload = json.loads(result.stdout)
    reasons = {s["reason"] for s in payload["skipped"] if s["path"] == "blob.py"}
    assert "binary" in reasons


def test_skip_reason_unreadable(tmp_path: Path) -> None:
    f = tmp_path / "noperm.py"
    f.write_text("x = 1\n")
    f.chmod(0o000)
    try:
        result = run_cli("--root", str(tmp_path), "noperm.py")
        payload = json.loads(result.stdout)
        reasons = {s["reason"] for s in payload["skipped"] if s["path"] == "noperm.py"}
        assert "unreadable" in reasons
    finally:
        f.chmod(0o644)


def test_skip_reason_out_of_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_x.py"
    outside.write_text("x = 1\n")
    try:
        root = tmp_path / "root"
        root.mkdir()
        result = run_cli("--root", str(root), "../outside_x.py")
        payload = json.loads(result.stdout)
        reasons = {s["reason"] for s in payload["skipped"] if s["path"] == "../outside_x.py"}
        assert "out-of-root" in reasons
    finally:
        outside.unlink()


# --- backtracking-shape lint -----------------------------------------------


@pytest.mark.parametrize(
    "pattern,expected",
    [
        ("(a+)+", True),
        ("(a*)*", True),
        ("(a+)*", True),
        ("a+b*", False),
        ("hx-[a-z-]+\\s*=", False),
    ],
)
def test_backtracking_shape_lint(pattern: str, expected: bool) -> None:
    assert panel_detect.has_catastrophic_backtracking_shape(pattern) is expected

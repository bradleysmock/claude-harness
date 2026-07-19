"""Integration tests: panel_detect.py CLI against the shipped triggers.md
(ticket 0057) — worked examples and --design-mode candidate emission."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "panel_detect.py"
TRIGGERS = ROOT / "context" / "panels" / "triggers.md"


def run_cli(root: Path, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_shipped_triggers_load_cleanly() -> None:
    sys.path.insert(0, str(ROOT))
    import panel_detect

    specs = panel_detect.load_triggers(TRIGGERS)
    panels_dir = ROOT / "context" / "panels"
    on_disk = {p.name for p in panels_dir.glob("*.md")} - {"core.md", "secondary.md", "triggers.md"}
    assert {spec.file for spec in specs.values()} == on_disk


# FR-4: judgment entries that are a near-miss to their own panel's deterministic
# fields must carry a provenance comment. Role-based judgment (no deterministic
# field to be a near-miss *of*) is exempt — pinned explicitly here so a future
# edit to either set forces a conscious decision rather than silent drift.
_NEAR_MISS_PANELS = {
    "react", "shell", "http-api", "graphql", "identity", "ui",
    "infrastructure", "ai-llm", "database", "performance",
}
_ROLE_BASED_EXEMPT_PANELS = {"observability", "distributed"}


def test_near_miss_judgment_entries_carry_provenance_comments() -> None:
    sys.path.insert(0, str(ROOT))
    import panel_detect

    specs = panel_detect.load_triggers(TRIGGERS)
    raw = TRIGGERS.read_text()
    judgment_panels = {k for k, v in specs.items() if v.judgment}
    assert judgment_panels == _NEAR_MISS_PANELS | _ROLE_BASED_EXEMPT_PANELS

    fences = re.findall(r"```toml\n(.*?)```", raw, re.DOTALL)
    lines = fences[0].splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("judgment = "):
            continue
        header = next(ln for ln in reversed(lines[:i]) if ln.startswith("[panels."))
        key = header[len("[panels."):-1]
        if key in _NEAR_MISS_PANELS:
            comment_block: list[str] = []
            j = i - 1
            while j >= 0 and lines[j].lstrip().startswith("#"):
                comment_block.append(lines[j].lstrip())
                j -= 1
            assert any(ln.startswith("# provenance:") for ln in comment_block), (
                f"panels.{key}'s judgment line has no preceding '# provenance:' comment"
            )


def test_python_route_handler_activates_core_python_http_api(tmp_path: Path) -> None:
    (tmp_path / "app" / "routes").mkdir(parents=True)
    (tmp_path / "app" / "routes" / "users.py").write_text("def get_users(): return []\n")
    payload = run_cli(tmp_path, "app/routes/users.py")
    assert [p["panel"] for p in payload["active"]] == ["core", "python", "http-api"]


def test_tsx_component_activates_core_typescript_ui(tmp_path: Path) -> None:
    (tmp_path / "Comp.tsx").write_text("export const C = () => <div/>;\n")
    payload = run_cli(tmp_path, "Comp.tsx")
    assert {p["panel"] for p in payload["active"]} == {"core", "typescript", "ui"}


def test_sql_migration_activates_core_database(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.sql").write_text("CREATE TABLE x (id int);\n")
    payload = run_cli(tmp_path, "migrations/001.sql")
    assert [p["panel"] for p in payload["active"]] == ["core", "database"]


def test_preact_dependency_does_not_activate_react_panel(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"preact": "^10.0.0"}}\n')
    (tmp_path / "app.js").write_text("export const x = 1;\n")
    payload = run_cli(tmp_path, "app.js")
    panels = {p["panel"] for p in payload["active"]}
    assert "react" not in panels
    assert "typescript" in panels


def test_design_mode_root_manifest_dep_activates(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"@angular/core": "^17.0.0"}}\n')
    (tmp_path / "angular.json").write_text("{}\n")
    payload = run_cli(tmp_path, "--design")
    panels = {p["panel"] for p in payload["active"]}
    assert "angular" in panels


def test_design_mode_never_silently_drops_content_dependent_panels(tmp_path: Path) -> None:
    payload = run_cli(tmp_path, "--design")
    active = {p["panel"] for p in payload["active"]}
    candidates = {c["panel"] for c in payload["candidates"]}
    # every non-core panel is accounted for: either active, or a visible candidate
    all_panels = active | candidates
    assert all_panels >= {
        "python", "typescript", "go", "rust", "http-api", "ui", "identity", "cryptography",
    }

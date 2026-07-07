"""FR-3: drift guard — documented hook/MCP-gate commands match the source.

Parses the "Hook <-> MCP gate command parity" table in
context/harness-reference.md (does NOT hardcode the commands), then asserts each
documented command's salient tokens appear as *code string constants* in the
corresponding layer's source. Matching against the parsed Python AST — not raw
file text — is deliberate: a flag echoed only in a comment or docstring must NOT
satisfy the check, so the guard actually bites when a hook command loses a
documented flag (e.g. Go's -race) even though an explanatory comment still
mentions it.

All twelve documented cells (four languages x per-write / stop / MCP) are
enforced, each mapped to the source file that implements it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
REFERENCE = ROOT / "context" / "harness-reference.md"

# Every documented (language, column) cell -> the source file implementing it.
LAYER_SOURCE = {
    ("Python", "per_write"): "hooks/post_write_gate.py",
    ("Python", "stop"): "hooks/stop_full_gate.py",
    ("Python", "mcp"): "gates/python.py",
    ("JS/TS", "per_write"): "hooks/post_write_gate.py",
    ("JS/TS", "stop"): "hooks/stop_full_gate.py",
    ("JS/TS", "mcp"): "gates/typescript.py",
    ("Go", "per_write"): "hooks/post_write_gate.py",
    ("Go", "stop"): "hooks/stop_full_gate.py",
    ("Go", "mcp"): "gates/go.py",
    ("Rust", "per_write"): "hooks/post_write_gate.py",
    ("Rust", "stop"): "hooks/stop_full_gate.py",
    ("Rust", "mcp"): "gates/rust.py",
}

COLUMNS = ("per_write", "stop", "mcp")


# --- reference-table parsing ----------------------------------------------

def _parity_section() -> str:
    text = REFERENCE.read_text(encoding="utf-8")
    start = text.index("### Hook")  # "### Hook <-> MCP gate command parity"
    rest = text[start + 1 :]
    end = rest.find("\n### ")
    return rest if end == -1 else rest[: end + 1]


def _parse_table() -> dict[str, dict[str, list[str]]]:
    """language -> {column -> [command strings]} parsed from the parity table."""
    parity: dict[str, dict[str, list[str]]] = {}
    for line in _parity_section().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        lang = cells[0]
        if lang in ("Language", "") or set(lang) <= {"-", ":", " "}:
            continue  # header or separator row
        parity[lang] = {col: re.findall(r"`([^`]+)`", cell) for col, cell in zip(COLUMNS, cells[1:])}
    return parity


# --- source introspection (AST, so comments/docstrings do not count) -------

def _code_string_constants(source: str) -> list[str]:
    """All string constants in the source AST, excluding docstrings.

    Comments never appear in the AST, so a flag mentioned only in a comment is
    invisible here — which is exactly what makes the drift guard bite.
    """
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def _salient_tokens(command: str) -> list[str]:
    """Executable + flag/subcommand tokens; drop path/glob tokens like ./...."""
    tokens = []
    for tok in command.split():
        if "/" in tok or tok == "." or set(tok) <= {"."}:
            continue
        tokens.append(tok)
    return tokens


def _assert_command_in_constants(command: str, constants: list[str], where: str) -> None:
    for tok in _salient_tokens(command):
        assert any(tok in c for c in constants), \
            f"documented token {tok!r} (from {command!r}) absent from {where} code constants"


PARITY = _parse_table()


def test_table_lists_all_languages():
    assert {"Python", "JS/TS", "Go", "Rust"} <= set(PARITY), f"parity table missing languages: {PARITY.keys()}"


def test_go_race_documented_on_both_layers():
    go = PARITY["Go"]
    assert any("-race" in c for c in go["stop"]), "Stop-hook Go command must document -race"
    assert any("-race" in c for c in go["mcp"]), "MCP-gate Go command must document -race"


def test_all_documented_cells_match_source():
    constants_cache: dict[str, list[str]] = {}
    for (lang, col), rel in LAYER_SOURCE.items():
        commands = PARITY[lang][col]
        assert commands, f"parity table has no {col} command for {lang}"
        if rel not in constants_cache:
            constants_cache[rel] = _code_string_constants((ROOT / rel).read_text(encoding="utf-8"))
        for command in commands:
            _assert_command_in_constants(command, constants_cache[rel], rel)


def test_race_is_a_real_constant_in_both_go_sources():
    # Not a comment mention — an actual argument constant.
    for rel in ("hooks/stop_full_gate.py", "gates/go.py"):
        consts = _code_string_constants((ROOT / rel).read_text(encoding="utf-8"))
        assert any("-race" in c for c in consts), f"{rel} must pass -race as a real command argument"


def test_guard_bites_on_command_regression_despite_comment():
    """Realistic regression: -race dropped from the command list but still named
    in the explanatory comment above it. The guard must still fail."""
    source = (ROOT / "hooks" / "stop_full_gate.py").read_text(encoding="utf-8")
    doctored = source.replace('"test", "-race", "./..."', '"test", "./..."')
    assert doctored != source, "fixture precondition: the Go test command literal must be present"
    assert "-race" in doctored, "the comment mention of -race must survive the doctoring"
    consts = _code_string_constants(doctored)
    with pytest.raises(AssertionError):
        for command in PARITY["Go"]["stop"]:
            _assert_command_in_constants(command, consts, "doctored")

"""Deterministic panel-activation detector (ticket 0057).

Reads the canonical trigger data in ``context/panels/triggers.md`` and maps
``(project root, in-scope files)`` to the set of expert-critique panels that
should activate. Replaces the old model-judgment prose table that used to
live in ``skills/critique/SKILL.md``.

CLI:
    panel_detect.py --root DIR [--triggers PATH] [--design] [FILE ...]

Prints one JSON object to stdout on success: ``active`` (Core first, then
trigger-table order, each with ``evidence``), ``candidates`` (judgment or
design-mode-unevaluated panels), and ``skipped`` (files that could not be
scanned, with a reason). On any trigger-data fault or invalid invocation,
prints a diagnostic to stderr and exits non-zero — no JSON is printed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:  # tomllib is stdlib on Python >= 3.11; tomli is the 3.10 backport
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter version
    import tomli as tomllib  # type: ignore[no-redef, import-not-found]  # 3.10-only backport, not installed under 3.11+

# Cap the amount of a file's content scanned for `content` trigger patterns,
# so a single huge or adversarial file can't blow up per-file scan cost.
_MAX_SCAN_BYTES = 512_000
_FENCE_RE = re.compile(r"```toml\n(.*?)```", re.DOTALL)
_ALLOWED_FIELDS = {"file", "globs", "manifests", "deps", "path_keywords", "content", "judgment"}
_LIST_FIELDS = ("globs", "manifests", "deps", "path_keywords", "content")

_JSON_MANIFESTS = {"package.json"}
_TOML_MANIFESTS = {"pyproject.toml", "Cargo.toml"}
_LINE_MANIFESTS = {"requirements.txt", "go.mod", "Gemfile"}
_MANIFEST_NAME_TOKEN = re.compile(r"^\s*(?:require\s+)?([A-Za-z0-9_.\-/@]+)")
_GEM_LINE = re.compile(r"gem\s+['\"]([^'\"]+)['\"]")

_NESTED_QUANTIFIER = re.compile(r"\([^()]*[+*][^()]*\)[+*]")


class TriggerDataError(ValueError):
    """Raised for any fault in triggers.md — always fatal (fail-closed)."""


def has_catastrophic_backtracking_shape(pattern: str) -> bool:
    """Heuristic ReDoS-shape lint: a quantified group whose own body is itself
    quantified, e.g. ``(a+)+`` or ``(a*)*`` — ambiguous repetition-of-repetition
    that can blow up exponentially on adversarial input."""
    return bool(_NESTED_QUANTIFIER.search(pattern))


@dataclass(frozen=True)
class PanelSpec:
    key: str
    file: str
    globs: tuple[str, ...] = ()
    manifests: tuple[str, ...] = ()
    deps: tuple[str, ...] = ()
    path_keywords: tuple[str, ...] = ()
    content: tuple[str, ...] = ()
    judgment: str = ""


@dataclass
class Evidence:
    kind: str
    path: str
    pattern: str

    def to_json(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path, "pattern": self.pattern}


def load_triggers(path: Path) -> dict[str, PanelSpec]:
    """Parse and validate triggers.md. Raises TriggerDataError on any fault."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TriggerDataError(f"cannot read triggers file {path}: {exc}") from exc

    fences = _FENCE_RE.findall(text)
    if len(fences) != 1:
        raise TriggerDataError(
            f"{path} must contain exactly one fenced ```toml block, found {len(fences)}"
        )

    try:
        data = tomllib.loads(fences[0])
    except tomllib.TOMLDecodeError as exc:
        raise TriggerDataError(f"{path} TOML block is unparseable: {exc}") from exc

    panels_raw = data.get("panels")
    if not isinstance(panels_raw, dict) or not panels_raw:
        raise TriggerDataError(f"{path} has no non-empty [panels.*] table")

    specs: dict[str, PanelSpec] = {}
    for key, raw in panels_raw.items():
        specs[key] = _parse_panel_spec(key, raw)

    return specs


def _parse_panel_spec(key: str, raw: object) -> PanelSpec:
    """Validate a single [panels.KEY] table and construct its PanelSpec.
    Raises TriggerDataError on any fault."""
    if not isinstance(raw, dict):
        raise TriggerDataError(f"panels.{key} must be a table")

    unknown = set(raw) - _ALLOWED_FIELDS
    if unknown:
        raise TriggerDataError(f"panels.{key} has unknown field(s): {sorted(unknown)}")

    file_name = raw.get("file")
    if not isinstance(file_name, str) or not file_name:
        raise TriggerDataError(f"panels.{key} is missing a string 'file' field")

    list_values: dict[str, tuple[str, ...]] = {}
    for field_name in _LIST_FIELDS:
        value = raw.get(field_name, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise TriggerDataError(f"panels.{key}.{field_name} must be a list of strings")
        list_values[field_name] = tuple(value)

    judgment = raw.get("judgment", "")
    if not isinstance(judgment, str):
        raise TriggerDataError(f"panels.{key}.judgment must be a string")

    for pattern in list_values["content"]:
        try:
            re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            raise TriggerDataError(
                f"panels.{key} content pattern {pattern!r} does not compile: {exc}"
            ) from exc
        if has_catastrophic_backtracking_shape(pattern):
            raise TriggerDataError(
                f"panels.{key} content pattern {pattern!r} has a catastrophic-backtracking shape"
            )

    return PanelSpec(
        key=key,
        file=file_name,
        globs=list_values["globs"],
        manifests=list_values["manifests"],
        deps=list_values["deps"],
        path_keywords=list_values["path_keywords"],
        content=list_values["content"],
        judgment=judgment,
    )


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern[i : i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _match_glob(pattern: str, relpath: str) -> bool:
    # A pattern with no '/' (e.g. `conftest.py`, `next.config.*`) is a bare
    # filename and matches by basename at any depth, not just at repo root;
    # a pattern containing '/' (e.g. `app/routes/**`, `.git/hooks/*`) anchors
    # against the full relative path instead. Both forms occur in triggers.md.
    target = relpath if "/" in pattern else PurePosixPath(relpath).name
    return bool(_glob_to_regex(pattern).match(target))


def _contained(root: Path, candidate: str) -> tuple[Path | None, str | None]:
    """Resolve candidate under root. Returns (resolved_path, None) on success,
    or (None, reason) — reason is one of 'unreadable', 'out-of-root', 'missing'."""
    try:
        root_resolved = root.resolve()
    except OSError:
        return None, "unreadable"
    candidate_path = Path(candidate)
    target = candidate_path if candidate_path.is_absolute() else root / candidate_path
    try:
        resolved = target.resolve()
    except OSError:
        return None, "unreadable"
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None, "out-of-root"
    if not resolved.is_file():
        return None, "missing"
    return resolved, None


def _read_capped(path: Path) -> tuple[str | None, str | None]:
    """Read path as capped UTF-8 text. Returns (text, skip_reason)."""
    try:
        size = path.stat().st_size
    except OSError:
        return None, "unreadable"
    if size > _MAX_SCAN_BYTES:
        return None, "oversize"
    try:
        raw = path.read_bytes()
    except OSError:
        return None, "unreadable"
    if b"\x00" in raw:
        return None, "binary"
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "binary"


def _dep_names_from_package_json(text: str) -> set[str]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return set()
    names: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        block = obj.get(section)
        if isinstance(block, dict):
            names.update(block.keys())
    return names


def _dep_names_from_toml_manifest(text: str) -> set[str]:
    try:
        obj = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return set()
    names: set[str] = set()
    project_deps = obj.get("project", {}).get("dependencies", [])
    for entry in project_deps:
        m = _MANIFEST_NAME_TOKEN.match(entry)
        if m:
            names.add(m.group(1))
    poetry_deps = obj.get("tool", {}).get("poetry", {}).get("dependencies", {})
    names.update(k for k in poetry_deps if k.lower() != "python")
    for section in ("dependencies", "dev-dependencies"):
        block = obj.get(section)
        if isinstance(block, dict):
            names.update(block.keys())
    return names


def _dep_names_from_requirements_txt(text: str) -> set[str]:
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        m = _MANIFEST_NAME_TOKEN.match(stripped)
        if m:
            names.add(m.group(1))
    return names


def _dep_names_from_go_mod(text: str) -> set[str]:
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped in ("require (", ")"):
            continue
        m = _MANIFEST_NAME_TOKEN.match(stripped)
        if m and m.group(1) not in ("module", "go"):
            names.add(m.group(1))
    return names


def _dep_names_from_gemfile(text: str) -> set[str]:
    return set(_GEM_LINE.findall(text))


def _dep_names_from_manifest(name: str, text: str) -> set[str]:
    if name == "package.json":
        return _dep_names_from_package_json(text)
    if name in ("pyproject.toml", "Cargo.toml"):
        return _dep_names_from_toml_manifest(text)
    if name == "requirements.txt":
        return _dep_names_from_requirements_txt(text)
    if name == "go.mod":
        return _dep_names_from_go_mod(text)
    if name == "Gemfile":
        return _dep_names_from_gemfile(text)
    return set()


class Detector:
    def __init__(self, root: Path, specs: dict[str, PanelSpec]) -> None:
        self.root = root
        self.specs = specs
        self._skipped: list[dict[str, str]] = []
        self._skipped_paths: set[str] = set()
        self._text_cache: dict[str, tuple[str | None, str | None]] = {}

    def _skip(self, relpath: str, reason: str) -> None:
        key = f"{relpath}:{reason}"
        if key in self._skipped_paths:
            return
        self._skipped_paths.add(key)
        self._skipped.append({"path": relpath, "reason": reason})

    def _text_of(self, relpath: str, resolved: Path) -> str | None:
        if relpath not in self._text_cache:
            self._text_cache[relpath] = _read_capped(resolved)
        text, reason = self._text_cache[relpath]
        if reason is not None:
            self._skip(relpath, reason)
        return text

    def _manifest_dep_names(self, manifest_relpath: str, resolved: Path) -> set[str]:
        text = self._text_of(manifest_relpath, resolved)
        if text is None:
            return set()
        basename = PurePosixPath(manifest_relpath).name
        return _dep_names_from_manifest(basename, text)

    def run(self, file_args: list[str], design: bool) -> dict:
        contained: list[tuple[str, Path]] = []
        for arg in sorted(file_args):
            resolved, reason = _contained(self.root, arg)
            if resolved is None:
                self._skip(arg, reason or "missing")
                continue
            contained.append((arg, resolved))

        manifest_candidates = self._collect_manifest_candidates(contained)

        active: list[dict] = [
            {
                "panel": "core",
                "file": "core.md",
                "evidence": [{"kind": "always", "path": "", "pattern": "core"}],
            }
        ]
        candidates: list[dict] = []

        for key, spec in self.specs.items():
            evidence = self._evaluate(spec, contained, manifest_candidates, design)
            if evidence:
                active.append({"panel": key, "file": spec.file, "evidence": [e.to_json() for e in evidence]})
                continue

            reasons: list[str] = []
            if design and (spec.globs or spec.path_keywords or spec.content):
                reasons.append(
                    "file-content-dependent trigger(s) not evaluated in --design mode"
                )
            if spec.judgment:
                reasons.append(spec.judgment)
            if reasons:
                candidates.append({"panel": key, "file": spec.file, "reasons": reasons})

        return {"active": active, "candidates": candidates, "skipped": self._skipped}

    def _collect_manifest_candidates(
        self, contained: list[tuple[str, Path]]
    ) -> list[tuple[str, Path]]:
        """Root-level manifest files plus any in-scope file matching a known
        manifest basename — the set eligible for structured `deps` parsing."""
        known = _JSON_MANIFESTS | _TOML_MANIFESTS | _LINE_MANIFESTS
        found: list[tuple[str, Path]] = []
        for name in sorted(known):
            root_candidate = self.root / name
            if root_candidate.is_file():
                found.append((name, root_candidate))
        for relpath, resolved in contained:
            if PurePosixPath(relpath).name in known:
                found.append((relpath, resolved))
        return found

    def _evaluate(
        self,
        spec: PanelSpec,
        contained: list[tuple[str, Path]],
        manifest_candidates: list[tuple[str, Path]],
        design: bool,
    ) -> list[Evidence]:
        evidence: list[Evidence] = []

        for pattern in spec.manifests:
            if (self.root / pattern).is_file():
                evidence.append(Evidence("manifest", pattern, pattern))
            elif not design:
                for relpath, _resolved in contained:
                    if PurePosixPath(relpath).name == pattern:
                        evidence.append(Evidence("manifest", relpath, pattern))

        if spec.deps:
            dep_set: set[str] = set()
            for manifest_relpath, resolved in manifest_candidates:
                dep_set |= self._manifest_dep_names(manifest_relpath, resolved)
            for dep in spec.deps:
                if dep in dep_set:
                    evidence.append(Evidence("dep", "manifest", dep))

        if design:
            return evidence

        for relpath, _resolved in contained:
            for pattern in spec.globs:
                if _match_glob(pattern, relpath):
                    evidence.append(Evidence("glob", relpath, pattern))
            lower = relpath.lower()
            for keyword in spec.path_keywords:
                if keyword.lower() in lower:
                    evidence.append(Evidence("path_keyword", relpath, keyword))

        for relpath, resolved in contained:
            if not spec.content:
                continue
            text = self._text_of(relpath, resolved)
            if text is None:
                continue
            for pattern in spec.content:
                if re.search(pattern, text, re.MULTILINE):
                    evidence.append(Evidence("content", relpath, pattern))

        return evidence


def _default_triggers_path() -> Path:
    return Path(__file__).resolve().parent / "context" / "panels" / "triggers.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--triggers", default=None)
    parser.add_argument("--design", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"panel_detect: --root {args.root!r} is not a directory", file=sys.stderr)
        return 2

    if not args.design and not args.files:
        print("panel_detect: at least one FILE is required unless --design is set", file=sys.stderr)
        return 2

    triggers_path = Path(args.triggers) if args.triggers else _default_triggers_path()
    try:
        specs = load_triggers(triggers_path)
    except TriggerDataError as exc:
        print(f"panel_detect: {exc}", file=sys.stderr)
        return 2

    detector = Detector(root, specs)
    result = detector.run(args.files, args.design)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

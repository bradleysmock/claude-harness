#!/usr/bin/env python3
"""PreToolUse hook: scan Write/Edit content for forbidden code shapes.

Polyglot — dispatches on file extension. Universal scanner (secrets, generic
SQL injection markers) runs on every file. Language scanners add language-
specific anti-patterns documented in `.claude/rules/<language>.md`.

Blocks the write (exit 2 with stderr) when a violation is found; the model
sees the stderr and self-corrects. Honors `nosec` / `nolint` / `eslint-disable`
style comments on the same line for justified exceptions.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Violation:
    rule_id: str
    line_number: int
    line_excerpt: str
    fix_hint: str


# --- Universal patterns ----------------------------------------------------

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bghp_[A-Za-z0-9]{30,}")),
    ("slack-bot-token", re.compile(r"\bxoxb-[A-Za-z0-9-]{20,}")),
    ("private-key-header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----")),
)

GENERIC_SQL_KEYWORDS = re.compile(r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)
PY_FSTRING_INTERPOLATION = re.compile(r"f['\"][^'\"]*\{")
JS_TEMPLATE_INTERPOLATION = re.compile(r"`[^`]*\$\{")
PERCENT_INTERPOLATION = re.compile(r"%\s*[(\w]")  # Python % formatting tail
GO_SPRINTF_INTERPOLATION = re.compile(r"\bSprintf\s*\(")

JUSTIFICATION_MARKERS = (
    "nosec",
    "nolint",
    "eslint-disable",
    "@ts-expect-error",
    "// cast:",
    "# noqa",
)


# --- Python patterns -------------------------------------------------------

PY_SHELL_TRUE = re.compile(r"\bshell\s*=\s*True\b")
PY_EVAL = re.compile(r"(?<![\w.])eval\s*\(")
PY_EXEC = re.compile(r"(?<![\w.])exec\s*\(")
PY_PICKLE_LOADS = re.compile(r"\bpickle\.loads\s*\(")
PY_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
PY_BROAD_EXCEPT = re.compile(r"^\s*except\s+Exception\s*(?:as\s+\w+\s*)?:")
PY_MUTABLE_DEFAULT = re.compile(
    r"def\s+\w+\s*\([^)]*=\s*(?:\[\s*\]|\{\s*\}|\{[^:}]*\})"
)


# --- JavaScript / TypeScript patterns --------------------------------------

JS_EVAL = re.compile(r"(?<![\w.])eval\s*\(")
JS_NEW_FUNCTION = re.compile(r"new\s+Function\s*\(")
JS_SETTIMEOUT_STRING = re.compile(r"\bsetTimeout\s*\(\s*['\"`]")
JS_SETINTERVAL_STRING = re.compile(r"\bsetInterval\s*\(\s*['\"`]")
JS_CHILD_PROCESS_EXEC = re.compile(r"\b(?:child_process\.)?execSync?\s*\(\s*[`'\"]")
JS_INNER_HTML_ASSIGN = re.compile(r"\.innerHTML\s*=\s*(?!['\"]\s*['\"])")
JS_DOC_WRITE = re.compile(r"\bdocument\.write\s*\(")
TS_AS_ANY = re.compile(r"\bas\s+any\b")
TS_TS_IGNORE = re.compile(r"@ts-ignore\b")
TS_TS_NOCHECK = re.compile(r"@ts-nocheck\b")


# --- Go patterns -----------------------------------------------------------

GO_PANIC = re.compile(r"\bpanic\s*\(")
GO_FMT_PRINTLN = re.compile(r"\bfmt\.Println\s*\(")
GO_EXEC_SH_C = re.compile(r"exec\.Command\s*\(\s*['\"]sh['\"]\s*,\s*['\"]-c['\"]")


# --- Rust patterns ---------------------------------------------------------

RS_UNWRAP = re.compile(r"\.unwrap\s*\(\s*\)")
RS_EXPECT = re.compile(r"\.expect\s*\(")
RS_PANIC = re.compile(r"\bpanic!\s*\(")
RS_PRINTLN = re.compile(r"\b(?:e?)println!\s*\(")
RS_UNSAFE = re.compile(r"\bunsafe\s*\{")


# --- Helpers ---------------------------------------------------------------

def line_has_justification(line: str) -> bool:
    return any(marker in line for marker in JUSTIFICATION_MARKERS)


def extension_of(file_path: str) -> str:
    return Path(file_path).suffix.lower()


def detect_languages(file_path: str) -> list[str]:
    ext = extension_of(file_path)
    if ext in (".py", ".pyi"):
        return ["python"]
    if ext in (".ts", ".tsx"):
        return ["typescript", "javascript"]
    if ext in (".js", ".jsx", ".mjs", ".cjs"):
        return ["javascript"]
    if ext == ".go":
        return ["go"]
    if ext == ".rs":
        return ["rust"]
    return []


# --- Scanners --------------------------------------------------------------

def scan_universal(file_path: str, line: str, line_number: int) -> list[Violation]:
    findings: list[Violation] = []
    has_justification = line_has_justification(line)

    for secret_name, pattern in SECRET_PATTERNS:
        if pattern.search(line):
            findings.append(Violation(
                rule_id=f"hardcoded-secret:{secret_name}",
                line_number=line_number,
                line_excerpt=line.strip()[:120],
                fix_hint="Read from environment or a secrets manager. Never hardcode credentials. If this is a fixture, use an obviously fake value like 'sk-test-FAKE-DO-NOT-USE'.",
            ))

    if GENERIC_SQL_KEYWORDS.search(line):
        if (
            PY_FSTRING_INTERPOLATION.search(line)
            or JS_TEMPLATE_INTERPOLATION.search(line)
            or PERCENT_INTERPOLATION.search(line)
            or GO_SPRINTF_INTERPOLATION.search(line)
        ) and not has_justification:
            findings.append(Violation(
                rule_id="sql-interpolation",
                line_number=line_number,
                line_excerpt=line.strip()[:120],
                fix_hint="Parameterize: use ?, $1, :name, or the ORM's bind syntax. Never interpolate user values into SQL.",
            ))

    return findings


def scan_python(file_path: str, line: str, line_number: int) -> list[Violation]:
    findings: list[Violation] = []
    has_justification = line_has_justification(line)

    if PY_SHELL_TRUE.search(line) and not has_justification:
        findings.append(Violation(
            rule_id="py:shell-true",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint='Pass argument list: subprocess.run(["cmd", arg1, arg2], check=True). Annotate as "# nosec: <reason>" only if genuinely required.',
        ))

    if PY_EVAL.search(line):
        findings.append(Violation(
            rule_id="py:eval",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Use ast.literal_eval for literals, json.loads for JSON, or an explicit parser.",
        ))

    if PY_EXEC.search(line):
        findings.append(Violation(
            rule_id="py:exec",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="exec() on dynamic input is a remote-code-execution risk. Rewrite to use explicit data handling.",
        ))

    if PY_PICKLE_LOADS.search(line):
        findings.append(Violation(
            rule_id="py:pickle-loads",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="pickle.loads on untrusted data executes arbitrary code. Use json or a schema-validated format.",
        ))

    if PY_BARE_EXCEPT.match(line):
        findings.append(Violation(
            rule_id="py:bare-except",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Catch the specific exception type. Bare except: also swallows KeyboardInterrupt and SystemExit.",
        ))

    if PY_BROAD_EXCEPT.match(line):
        findings.append(Violation(
            rule_id="py:broad-except",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Catch the specific exception. If a broad catch is needed at a boundary, logger.exception() and re-raise.",
        ))

    if PY_MUTABLE_DEFAULT.search(line):
        findings.append(Violation(
            rule_id="py:mutable-default-arg",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Default to None and instantiate inside: def f(items=None): items = list(items) if items is not None else []",
        ))

    return findings


def scan_javascript(file_path: str, line: str, line_number: int) -> list[Violation]:
    findings: list[Violation] = []
    has_justification = line_has_justification(line)

    if JS_EVAL.search(line):
        findings.append(Violation(
            rule_id="js:eval",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="eval on dynamic input is a remote-code-execution risk. Use JSON.parse or an explicit parser.",
        ))

    if JS_NEW_FUNCTION.search(line):
        findings.append(Violation(
            rule_id="js:new-function",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="new Function(string) is equivalent to eval. Refactor to use functions, not strings.",
        ))

    if JS_SETTIMEOUT_STRING.search(line) or JS_SETINTERVAL_STRING.search(line):
        findings.append(Violation(
            rule_id="js:timer-string",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="setTimeout/setInterval must take a function, not a string. Strings are evaluated as code.",
        ))

    if JS_CHILD_PROCESS_EXEC.search(line) and not has_justification:
        findings.append(Violation(
            rule_id="js:child-process-exec",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint='Use execFile or spawn with argument arrays: execFile("cmd", [arg1, arg2]). exec(string) shells out and is vulnerable to injection.',
        ))

    if JS_INNER_HTML_ASSIGN.search(line) and not has_justification:
        findings.append(Violation(
            rule_id="js:inner-html",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Use .textContent for plain text. For HTML, sanitize with DOMPurify and annotate the call site.",
        ))

    if JS_DOC_WRITE.search(line):
        findings.append(Violation(
            rule_id="js:document-write",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="document.write is unsafe and obsolete. Use DOM APIs (createElement, appendChild) or innerHTML with a sanitizer.",
        ))

    return findings


def scan_typescript(file_path: str, line: str, line_number: int) -> list[Violation]:
    findings: list[Violation] = []

    if TS_AS_ANY.search(line):
        findings.append(Violation(
            rule_id="ts:as-any",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Use 'unknown' and narrow with a type guard. 'as any' is a type-system bypass.",
        ))

    if TS_TS_IGNORE.search(line):
        findings.append(Violation(
            rule_id="ts:ts-ignore",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Use '@ts-expect-error — <reason>' instead — it auto-removes once the underlying issue is fixed.",
        ))

    if TS_TS_NOCHECK.search(line):
        findings.append(Violation(
            rule_id="ts:ts-nocheck",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Exclude the file in tsconfig.json instead of disabling type-checking for an entire file silently.",
        ))

    return findings


def scan_go(file_path: str, line: str, line_number: int) -> list[Violation]:
    findings: list[Violation] = []
    has_justification = line_has_justification(line)

    if GO_EXEC_SH_C.search(line) and not has_justification:
        findings.append(Violation(
            rule_id="go:exec-sh-c",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint='Use exec.Command("cmd", arg1, arg2) with argument list. exec.Command("sh", "-c", concatenated) shells out and is vulnerable to injection.',
        ))

    if GO_PANIC.search(line) and not has_justification:
        findings.append(Violation(
            rule_id="go:panic",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Return an error. panic() is for unrecoverable invariant violations at startup, not request-path code.",
        ))

    return findings


def scan_rust(file_path: str, line: str, line_number: int) -> list[Violation]:
    findings: list[Violation] = []
    has_justification = line_has_justification(line)

    is_test_context = "#[test]" in line or "#[cfg(test)]" in line or "/test" in file_path.lower()

    if RS_PANIC.search(line) and not has_justification and not is_test_context:
        findings.append(Violation(
            rule_id="rs:panic",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Return Result. panic! is for unrecoverable invariant violations.",
        ))

    if RS_UNSAFE.search(line) and not has_justification:
        findings.append(Violation(
            rule_id="rs:unsafe-no-comment",
            line_number=line_number,
            line_excerpt=line.strip()[:120],
            fix_hint="Annotate the unsafe block with a comment stating (1) the upheld invariant and (2) why safe alternatives are unsuitable.",
        ))

    return findings


SCANNERS: dict[str, Callable[[str, str, int], list[Violation]]] = {
    "python": scan_python,
    "javascript": scan_javascript,
    "typescript": scan_typescript,
    "go": scan_go,
    "rust": scan_rust,
}


# --- Top level -------------------------------------------------------------

def find_violations(file_path: str, content: str) -> list[Violation]:
    languages = detect_languages(file_path)
    findings: list[Violation] = []

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        findings.extend(scan_universal(file_path, raw_line, line_number))
        for language in languages:
            scanner = SCANNERS.get(language)
            if scanner is not None:
                findings.extend(scanner(file_path, raw_line, line_number))

    return findings


def extract_proposed_content(tool_name: str, tool_input: dict) -> tuple[str, str] | None:
    if tool_name == "Write":
        return tool_input.get("file_path", ""), tool_input.get("content", "")
    if tool_name == "Edit":
        return tool_input.get("file_path", ""), tool_input.get("new_string", "")
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        combined = "\n".join(edit.get("new_string", "") for edit in edits)
        return tool_input.get("file_path", ""), combined
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    extracted = extract_proposed_content(tool_name, tool_input)
    if extracted is None:
        return 0

    file_path, content = extracted
    if not content:
        return 0

    violations = find_violations(file_path, content)
    if not violations:
        return 0

    sys.stderr.write(
        "pre_write_guard blocked the write — Code Generation Rules violated:\n\n"
    )
    for violation in violations:
        sys.stderr.write(
            f"  [{violation.rule_id}] {Path(file_path).name}:{violation.line_number}\n"
            f"    > {violation.line_excerpt}\n"
            f"    fix: {violation.fix_hint}\n\n"
        )
    sys.stderr.write(
        "Fix the shape and retry. Do not add a suppression comment to silence this. "
        "See `.claude/rules/<language>.md` for the full rule details.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

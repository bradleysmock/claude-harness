"""Test flakiness detector — re-run the suite N times and find non-deterministic tests.

A gate failure is not always a real regression: a test may pass on one run and fail
on the next because of timing, environment state, or an external dependency. This
module re-runs the project's test suite ``runs`` times in sequence, records each
test's per-run PASSED/FAILED outcome, and reports the tests whose outcome *varies*
across runs (at least one pass **and** at least one fail). Consistent all-pass and
all-fail tests are never flaky and are excluded.

Two artifacts are produced by :func:`write_reports`:

* ``.harness/flaky-report.json`` — the machine-parseable IPC contract read by the
  ``/gate`` annotation step (:func:`annotate_failures`).
* ``.harness/flaky-report.md`` — a human-readable ranked view (fail rate descending).

Trust boundary: ``directory`` is resolved and verified contained within
``project_root`` *before* any subprocess runs (:func:`run_detection`); a path that
escapes the project root raises ``ValueError`` and aborts. The annotation step fails
closed — an absent, unreadable, or malformed report leaves every failure a hard
blocker.

Note on ``--threshold``: the exclusion rule is the literal ``pass_rate < threshold``.
The default is ``0.0`` (report every detected flaky test). requirements.md FR-7 names
a default of ``1.0``, but that is inconsistent with its own acceptance criteria — a
1.0 default would exclude every flaky test (all have pass_rate < 1.0), making the
default report always empty and contradicting "a test that fails in 2 of 5 runs
appears with pass rate 3/5". The acceptance criteria are the binding behavioral
contract, so the functional default is 0.0. This deviation is surfaced to the lead.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: A pytest ``-v`` result line: ``<nodeid> PASSED/FAILED/ERROR   [ 42%]``. The
#: nodeid is any non-space run containing ``::`` (file::test); trailing progress
#: percentages and durations are ignored.
_RESULT_LINE = re.compile(r"^(?P<node>\S+::\S+)\s+(?P<status>PASSED|FAILED|ERROR)\b")

DEFAULT_RUNS = 5
DEFAULT_THRESHOLD = 0.0


@dataclass(frozen=True)
class FlakyTest:
    """One test whose outcome varied across the detection runs.

    ``passes`` is the number of runs in which the test passed; ``runs`` is the
    detector's total run count (the denominator for the pass rate).
    """

    name: str
    passes: int
    runs: int

    @property
    def pass_rate(self) -> float:
        return self.passes / self.runs if self.runs else 0.0

    @property
    def fail_rate(self) -> float:
        return 1.0 - self.pass_rate

    @property
    def display(self) -> str:
        """Human-readable pass count, e.g. ``3/5 passed``."""
        return f"{self.passes}/{self.runs} passed"

    def to_json_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passes": self.passes, "runs": self.runs}

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> FlakyTest:
        return cls(name=str(data["name"]), passes=int(data["passes"]), runs=int(data["runs"]))


@dataclass(frozen=True)
class FlakyReport:
    """The set of flaky tests found in one detector run, plus the run count."""

    tests: list[FlakyTest]
    runs: int

    def to_json_dict(self) -> dict[str, Any]:
        return {"runs": self.runs, "tests": [t.to_json_dict() for t in self.tests]}

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> FlakyReport:
        if not isinstance(data, dict) or "runs" not in data or "tests" not in data:
            raise ValueError("flaky report is missing required keys 'runs'/'tests'")
        raw_tests = data["tests"]
        if not isinstance(raw_tests, list):
            raise ValueError("flaky report 'tests' must be a list")
        return cls(
            tests=[FlakyTest.from_json_dict(t) for t in raw_tests],
            runs=int(data["runs"]),
        )

    def to_markdown(self, generated_at: str) -> str:
        """Render the human-readable ranked report (fail rate descending)."""
        lines = [
            "# Flaky Test Report",
            "",
            f"**Generated at**: {generated_at}",
            f"**Runs**: {self.runs}",
            "",
        ]
        if not self.tests:
            lines.append("No flaky tests detected.")
            return "\n".join(lines) + "\n"
        lines += ["| Test | Pass rate | Fail rate |", "|---|---|---|"]
        for t in self.tests:
            lines.append(f"| `{t.name}` | {t.display} | {t.fail_rate:.0%} |")
        return "\n".join(lines) + "\n"


def _ranked(tests: list[FlakyTest]) -> list[FlakyTest]:
    """Sort by fail rate descending, name ascending for a stable tiebreak."""
    return sorted(tests, key=lambda t: (-t.fail_rate, t.name))


def _parse_run(output: str) -> dict[str, bool]:
    """Map each test nodeid to ``True`` (passed) / ``False`` (failed) for one run.

    Parses pytest ``-v`` output; PASSED is a pass, FAILED and ERROR are failures.
    """
    results: dict[str, bool] = {}
    for line in output.splitlines():
        match = _RESULT_LINE.match(line.strip())
        if match:
            results[match.group("node")] = match.group("status") == "PASSED"
    return results


def _run_pytest_once(directory: Path, timeout: int = 300) -> str:
    """Run the test suite once with machine-parseable per-test output.

    Returns pytest's combined stdout/stderr. Isolated in its own function so unit
    tests can substitute deterministic output without a real subprocess.
    """
    proc = subprocess.run(  # noqa: S603 — fixed argument list, no shell, contained dir
        [sys.executable, "-m", "pytest", "--tb=no", "-v", str(directory)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.stdout + proc.stderr


def run_detection(
    directory: Path,
    runs: int = DEFAULT_RUNS,
    threshold: float = DEFAULT_THRESHOLD,
    project_root: Path | None = None,
) -> FlakyReport:
    """Re-run the suite in ``directory`` ``runs`` times and return the flaky tests.

    A test is flaky when it passed at least once **and** failed at least once across
    the runs, and its pass rate is not below ``threshold`` (``pass_rate < threshold``
    tests are excluded — treated as blockers). ``directory`` is resolved and verified
    contained within ``project_root`` before any subprocess is launched; a directory
    that escapes the root raises ``ValueError``.
    """
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0.0, 1.0], got {threshold}")

    root = Path(project_root if project_root is not None else directory).resolve()
    resolved = Path(directory).resolve()
    # Containment guard — raises ValueError if `directory` escapes `project_root`.
    resolved.relative_to(root)

    pass_counts: dict[str, int] = {}
    seen_counts: dict[str, int] = {}
    for _ in range(runs):
        for node, passed in _parse_run(_run_pytest_once(resolved)).items():
            seen_counts[node] = seen_counts.get(node, 0) + 1
            pass_counts[node] = pass_counts.get(node, 0) + (1 if passed else 0)

    flaky: list[FlakyTest] = []
    for node, seen in seen_counts.items():
        passes = pass_counts.get(node, 0)
        fails = seen - passes
        if passes >= 1 and fails >= 1:
            candidate = FlakyTest(name=node, passes=passes, runs=runs)
            if candidate.pass_rate >= threshold:
                flaky.append(candidate)

    return FlakyReport(tests=_ranked(flaky), runs=runs)


def write_reports(
    report: FlakyReport,
    harness_dir: Path,
    generated_at: str | None = None,
) -> tuple[Path, Path]:
    """Write ``flaky-report.json`` and ``flaky-report.md`` under ``harness_dir``.

    The JSON is the deterministic machine contract (no timestamp); the timestamp
    lives only in the Markdown header so the JSON stays byte-stable across runs.
    Returns ``(json_path, md_path)``.
    """
    harness_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    json_path = harness_dir / "flaky-report.json"
    md_path = harness_dir / "flaky-report.md"
    json_path.write_text(
        json.dumps(report.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(report.to_markdown(stamp), encoding="utf-8")
    return json_path, md_path


def load_report(report_path: Path) -> FlakyReport:
    """Load and validate a flaky report from ``report_path`` (may raise)."""
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return FlakyReport.from_json_dict(data)


def _short_name(node: str) -> str:
    """The test function portion of a pytest nodeid (after the last ``::``)."""
    return node.rsplit("::", 1)[-1]


def _failure_matches(failure: str, nodeid: str) -> bool:
    """True when ``failure`` references the test ``nodeid``.

    A match requires the full nodeid *or* the test's short name to appear in
    ``failure`` bounded by non-identifier characters. The boundary on **both** forms
    is what keeps this fail-closed: an unanchored substring test would let a flaky
    ``tests/t.py::test_a`` label an unrelated failing ``tests/t.py::test_alpha`` /
    ``test_ab``, dismissing a genuine regression as "known flaky". Both the standard
    ``FAILED <nodeid> - <err>`` gate line and the bare short-name token (which
    ``_test_gate_dir`` emits after splitting on ``::``) are matched.

    Matching on the short name is deliberately file-agnostic — a bare short-name
    failure carries no path, so a flaky ``a.py::test_a`` can still match a failing
    ``b.py::test_a``; that is the best resolution available without a path in the
    failure text and is a false-*match* toward "flaky", never a false-miss.
    """
    for token in (nodeid, _short_name(nodeid)):
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", failure):
            return True
    return False


def annotate_failures(failures: list[str], report_path: Path) -> list[str]:
    """Annotate gate ``failures`` that match a known-flaky test, in memory.

    Each failure string that references a flaky test (by nodeid or by the test's
    short name) gets a ``— known flaky (X/N)`` suffix. **Fail closed**: if
    ``report_path`` is absent, unreadable, or malformed, every failure is returned
    unchanged (all remain hard blockers) and the error is logged. Returns a new list;
    the input is not mutated.
    """
    try:
        report = load_report(report_path)
    except FileNotFoundError:
        logger.warning("flaky report %s not found — all failures remain hard blockers", report_path)
        return list(failures)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        logger.exception(
            "flaky report %s is unreadable or malformed — all failures remain hard blockers",
            report_path,
        )
        return list(failures)

    annotated: list[str] = []
    for failure in failures:
        label = ""
        for test in report.tests:
            if _failure_matches(failure, test.name):
                label = f" — known flaky ({test.passes}/{test.runs})"
                break
        annotated.append(failure + label)
    return annotated

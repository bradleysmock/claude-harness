"""Data-driven promotion policy (ticket 0074).

Centralizes "which gates block delivery, and what happens when one fails" into
one declarative table plus one pure evaluator, instead of the assumption —
implicit in every suite runner — that every gate is required and any failure
blocks. ``load_policy``/``evaluate_promotion`` do no I/O and no subprocess; the
caller (``commands/gate.md``, ``build-ticket.md``) supplies already-computed
``GateResult``/``LanguageResult`` objects and reads the returned verdict.

Gate keys use one of two namespaces, since the runtime genuinely has two kinds
of gate: ``<language>.<gate>`` for gates dispatched per detected language
(including the cross-cutting ``secrets``/``coverage``/``dep-audit``/``sast``
phases, which re-run once per language — see ``gates/__init__.py``'s
``run_suite_on_dir``), and ``global.<gate>`` for a gate that runs exactly once,
independent of language (``commit_lint``). A bare, undotted name is rejected —
one explicit namespace per gate, never an ambiguous shared one.

These validation tables are intentionally separate from ``gates/config.py``'s
``_VALID_GATES``: that table scopes *overridable commands* (a narrower
purpose), so reusing it verbatim would make ``secrets``/``commit_lint``
unwritable in policy.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from gates.config import extract_policy_block
from models import GateResult, LanguageResult, StackName

#: Every gate a `run_suite_on_dir` call can append per language: the
#: overridable ones (mirroring `gates/config.py`'s `_VALID_GATES`) plus the
#: cross-cutting secrets/coverage/dep-audit/sast phases, which re-run once
#: per detected language rather than once globally.
_POLICY_LANGUAGE_GATES: dict[str, frozenset[str]] = {
    StackName.PYTHON.value: frozenset({
        "lint", "type_check", "test", "security",
        "secrets", "coverage", "dep-audit", "sast",
    }),
    StackName.TYPESCRIPT.value: frozenset({
        "type_check", "lint", "test",
        "secrets", "coverage", "dep-audit", "sast",
    }),
    StackName.GO.value: frozenset({
        "build", "vet", "test",
        "secrets", "coverage", "dep-audit", "sast",
    }),
    StackName.RUST.value: frozenset({
        "check", "clippy", "test",
        "secrets", "coverage", "dep-audit", "sast",
    }),
}

#: Gates that run once, independent of any language dispatch.
_POLICY_GLOBAL_GATES: frozenset[str] = frozenset({"commit_lint"})

#: Outcome severity ordering — the worst one across all required gates wins.
_SEVERITY_RANK: dict[str, int] = {"promote": 0, "pause_for_human": 1, "block": 2}

_POLICY_FIELDS = frozenset({"required", "on_block", "depends_on"})


class PolicyConfigError(ValueError):
    """Raised when a `[policy]` rule or `depends_on` reference is malformed."""


@dataclass(frozen=True)
class PolicyRule:
    gate: str
    required: bool
    on_block: Literal["fail", "pause_for_human", "warn"]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromotionVerdict:
    outcome: Literal["promote", "block", "pause_for_human"]
    blocking_gates: tuple[str, ...]
    reasons: tuple[str, ...]


def _validate_gate_ref(ref: str) -> None:
    """Raise :class:`PolicyConfigError` unless ``ref`` names a known gate."""
    language, _, gate = ref.partition(".")
    if language == "global":
        if gate not in _POLICY_GLOBAL_GATES:
            raise PolicyConfigError(f"unknown global policy gate: {ref!r}")
        return
    valid_gates = _POLICY_LANGUAGE_GATES.get(language)
    if valid_gates is None:
        raise PolicyConfigError(f"unknown policy language: {language!r} in {ref!r}")
    if gate not in valid_gates:
        raise PolicyConfigError(f"unknown gate {gate!r} for {language!r} in {ref!r}")


def _default_rules() -> list[PolicyRule]:
    rules: list[PolicyRule] = []
    for language, gates in sorted(_POLICY_LANGUAGE_GATES.items()):
        for gate in sorted(gates):
            rules.append(PolicyRule(gate=f"{language}.{gate}", required=True, on_block="fail"))
    for gate in sorted(_POLICY_GLOBAL_GATES):
        rules.append(PolicyRule(gate=f"global.{gate}", required=True, on_block="fail"))
    return rules


def _parse_bool(value: str) -> bool:
    token = value.strip().strip("\"'").lower()
    if token == "true":
        return True
    if token == "false":
        return False
    raise PolicyConfigError(f"expected true/false, got {value!r}")


def _parse_quoted(value: str) -> str:
    value = value.strip()
    if len(value) < 2 or value[0] not in "\"'" or value[-1] != value[0]:
        raise PolicyConfigError(f"expected a quoted string, got {value!r}")
    return value[1:-1]


def load_policy(standards_text: str) -> list[PolicyRule]:
    """Parse the `[policy]` sub-block of `standards_text`'s `[gates]` fence.

    No `[policy]` block yields the default policy: every known gate
    `required=True, on_block="fail"` — today's exact behavior, additive by
    default. Fail-closed: a malformed line, an unknown gate namespace, an
    invalid `on_block`, or an unresolvable `depends_on` reference raises
    :class:`PolicyConfigError` rather than silently applying a default.
    """
    rules_by_gate: dict[str, PolicyRule] = {rule.gate: rule for rule in _default_rules()}

    block = extract_policy_block(standards_text)
    if block is None:
        return list(rules_by_gate.values())

    for raw in block:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PolicyConfigError(f"malformed policy line (no '='): {line!r}")
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        parts = key.split(".")
        if len(parts) != 3:
            raise PolicyConfigError(
                f"policy key must be '<language>.<gate>.<field>' or "
                f"'global.<gate>.<field>': {key!r}"
            )
        gate_ref = f"{parts[0]}.{parts[1]}"
        field = parts[2]
        _validate_gate_ref(gate_ref)
        if field not in _POLICY_FIELDS:
            raise PolicyConfigError(f"unknown policy field: {field!r}")
        current = rules_by_gate.get(gate_ref)
        if current is None:
            raise PolicyConfigError(f"unknown policy gate: {gate_ref!r}")

        if field == "required":
            rules_by_gate[gate_ref] = replace(current, required=_parse_bool(value))
        elif field == "on_block":
            raw_on_block = _parse_quoted(value)
            if raw_on_block == "fail":
                rules_by_gate[gate_ref] = replace(current, on_block="fail")
            elif raw_on_block == "pause_for_human":
                rules_by_gate[gate_ref] = replace(current, on_block="pause_for_human")
            elif raw_on_block == "warn":
                rules_by_gate[gate_ref] = replace(current, on_block="warn")
            else:
                raise PolicyConfigError(f"invalid on_block value: {raw_on_block!r}")
        else:  # depends_on
            deps_text = _parse_quoted(value)
            deps = tuple(d.strip() for d in deps_text.split(",") if d.strip())
            for dep in deps:
                _validate_gate_ref(dep)
            rules_by_gate[gate_ref] = replace(current, depends_on=deps)

    return list(rules_by_gate.values())


def evaluate_promotion(
    language_results: list[LanguageResult],
    global_results: list[GateResult],
    policy: list[PolicyRule],
) -> PromotionVerdict:
    """Evaluate gate results against ``policy``. Pure — no I/O, no subprocess.

    ``reasons`` always lists every evaluated gate's verdict, in full, never
    suppressed. ``depends_on`` affects only ``blocking_gates`` — a failed
    gate is omitted there when a gate it depends on also failed (presumed a
    downstream symptom, not an independent root cause) — ``outcome`` severity
    is computed from every required gate's disposition regardless, so
    suppression never hides a real block/pause.
    """
    policy_by_gate = {rule.gate: rule for rule in policy}

    entries: list[tuple[str, PolicyRule, GateResult]] = []
    for language_result in language_results:
        for result in language_result.results:
            key = f"{language_result.language}.{result.gate}"
            rule = policy_by_gate.get(key)
            if rule is not None:
                entries.append((key, rule, result))
    for result in global_results:
        key = f"global.{result.gate}"
        rule = policy_by_gate.get(key)
        if rule is not None:
            entries.append((key, rule, result))

    reasons: list[str] = []
    severities: dict[str, str] = {}
    failed_keys: set[str] = set()

    for key, rule, result in entries:
        state = "skipped" if result.skipped else ("passed" if result.passed else "failed")
        reasons.append(f"{key}: {rule.on_block} ({state})")
        if result.skipped or result.passed:
            continue
        failed_keys.add(key)
        if not rule.required:
            continue
        if rule.on_block == "fail":
            severities[key] = "block"
        elif rule.on_block == "pause_for_human":
            severities[key] = "pause_for_human"
        # "warn" contributes no severity.

    outcome: Literal["promote", "block", "pause_for_human"] = "promote"
    for severity in severities.values():
        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[outcome]:
            outcome = severity  # type: ignore[assignment]

    blocking_gates: list[str] = []
    for key in severities:
        rule = policy_by_gate[key]
        if any(dep in failed_keys for dep in rule.depends_on):
            continue
        blocking_gates.append(key)

    return PromotionVerdict(
        outcome=outcome,
        blocking_gates=tuple(blocking_gates),
        reasons=tuple(reasons),
    )

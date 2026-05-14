"""
Prompt construction for generation and repair.
PromptBuilder is the single source of truth for all LLM instructions.
"""

from __future__ import annotations
import json
from string import Template
from ..models import GeneratedArtifact, GateError, RepairContext, Spec

SYSTEM_PROMPT = """\
You are a senior software engineer operating inside an automated coding harness.

## Your job
Given a specification, produce a complete, correct implementation and its test suite.

## Non-negotiable rules
1. Reason through the problem fully before writing any code.
2. Be explicit about every assumption you make.
3. Write complete code — no TODOs, no placeholders, no ellipses.
4. Tests must be self-contained and runnable without modification.
5. Follow every constraint in the spec exactly. If you cannot, state it in assumptions.

## Output format
Respond with a single JSON object matching this schema exactly.
Do not include markdown fences, preamble, or any text outside the JSON object.

Schema:
$schema
"""

GENERATE_PROMPT = """\
## Specification
$description

## Constraints
$constraints

## Acceptance criteria
$criteria

## Relevant codebase context
The following examples are drawn from the actual codebase this code will live in.
Match their patterns, naming conventions, and style precisely.

$examples
"""

REPAIR_PROMPT = """\
## Your previous attempt failed at the $failed_gate gate.

## Errors to fix
$errors

## Your previous reasoning
$previous_reasoning

## Your previous implementation
```
$previous_code
```

## Similar failures seen before
$similar_failures

## Instruction
$instruction
Fix only what is listed above. Do not restructure, rename, or refactor anything else.
Produce a complete corrected version — not a diff.
"""


class PromptBuilder:
    def __init__(self):
        self._schema = json.dumps(GeneratedArtifact.model_json_schema(), indent=2)
        self._system = Template(SYSTEM_PROMPT).substitute(schema=self._schema)

    @property
    def system(self) -> str:
        return self._system

    def generate(self, spec: Spec) -> str:
        return Template(GENERATE_PROMPT).substitute(
            description=spec.description,
            constraints=self._bullet(spec.constraints),
            criteria=self._bullet(spec.acceptance_criteria),
            examples=self._format_examples(spec.examples),
        )

    def repair(self, artifact: GeneratedArtifact, ctx: RepairContext) -> str:
        return Template(REPAIR_PROMPT).substitute(
            failed_gate=ctx.failed_gate,
            errors=self._format_errors(ctx.errors),
            previous_reasoning=artifact.reasoning,
            previous_code=artifact.implementation,
            similar_failures=self._bullet(ctx.similar_past_failures) or "None recorded.",
            instruction=ctx.instruction,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _bullet(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "None."

    def _format_examples(self, examples: list[str]) -> str:
        return "\n\n---\n\n".join(examples) if examples else "No examples retrieved."

    def _format_errors(self, errors: list[GateError]) -> str:
        lines = []
        for e in errors:
            location = f"{e.file}:{e.line}" if e.file and e.line else "unknown"
            lines.append(f"[{e.code or e.severity}] {location} — {e.message}")
        return "\n".join(lines)

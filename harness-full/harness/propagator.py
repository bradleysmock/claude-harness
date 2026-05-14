"""
Context propagation between dependent specs.

When Spec A completes, Spec B (which depends on A) receives:
  - A's exact public API extracted via AST (deterministic, not RAG)
  - A's full implementation as a reference example
  - The precise import path for A's module

This is the core mechanism that makes multi-spec tasks coherent:
downstream specs know exactly what upstream specs produced.
"""

from __future__ import annotations
import ast
from .models import Spec
from .task_models import SpecRun


class ContextPropagator:
    """
    Enriches a spec with deterministic context from its completed upstream deps.
    Called by TaskOrchestrator immediately before submitting each spec to the harness.
    """

    def enrich(self, spec: Spec, completed_runs: list[SpecRun]) -> Spec:
        """Return a copy of spec with upstream API constraints and examples injected."""
        injected_constraints: list[str] = []
        injected_examples: list[str] = []

        for sr in completed_runs:
            if sr.run.outcome != "passed":
                continue

            artifact = sr.run.attempts[-1].artifact
            target = sr.task_spec.spec.metadata.get("target_file", "unknown")
            api = self._extract_public_api(artifact.implementation, target)
            module_import = self._to_import_line(target)

            injected_constraints.append(
                f"GENERATED DEPENDENCY — {sr.task_spec.spec.id}\n"
                f"  File:   {target}\n"
                f"  Import: {module_import}\n"
                f"  Public API:\n"
                + "\n".join(f"    {line}" for line in api.splitlines())
            )
            injected_examples.append(
                f"### GENERATED DEPENDENCY: {sr.task_spec.spec.id} ({target})\n\n"
                f"```python\n{artifact.implementation}\n```"
            )

        if not injected_constraints:
            return spec

        return Spec(
            id=spec.id,
            description=spec.description,
            # Prepend — deps must be visible before other constraints
            constraints=injected_constraints + spec.constraints,
            acceptance_criteria=spec.acceptance_criteria,
            examples=injected_examples + spec.examples,
            metadata=spec.metadata,
        )

    # ── API extraction ────────────────────────────────────────────────────────

    def _extract_public_api(self, source: str, file_path: str) -> str:
        """
        Parse source with ast, extract public classes/functions with signatures.
        Returns a compact, formatted string suitable for injection into a prompt.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return f"(parse error — see full implementation in examples)"

        lines: list[str] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                lines.append(f"class {node.name}:")
                for item in node.body:
                    if (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and not item.name.startswith("_")):
                        lines.append(f"    {self._sig(item)}")
                lines.append("")

            elif (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and not node.name.startswith("_")):
                lines.append(self._sig(node))

        return "\n".join(lines).strip() or "(no public API detected)"

    def _sig(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Format a function/method signature from its AST node."""
        args: list[str] = []
        fn_args = node.args
        defaults_offset = len(fn_args.args) - len(fn_args.defaults)

        for i, arg in enumerate(fn_args.args):
            if arg.arg == "self":
                continue
            ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            didx = i - defaults_offset
            default = f" = {ast.unparse(fn_args.defaults[didx])}" if didx >= 0 else ""
            args.append(f"{arg.arg}{ann}{default}")

        if fn_args.vararg:
            ann = f": {ast.unparse(fn_args.vararg.annotation)}" \
                  if fn_args.vararg.annotation else ""
            args.append(f"*{fn_args.vararg.arg}{ann}")

        if fn_args.kwarg:
            ann = f": {ast.unparse(fn_args.kwarg.annotation)}" \
                  if fn_args.kwarg.annotation else ""
            args.append(f"**{fn_args.kwarg.arg}{ann}")

        ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)}){ret}"

    @staticmethod
    def _to_import_line(file_path: str) -> str:
        """Convert src/core/redis_rate_limiter.py → from core.redis_rate_limiter import ..."""
        path = file_path
        for prefix in ("src/", "./src/", "./"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        module = path.replace("/", ".").removesuffix(".py")
        return f"from {module} import ..."

# TypeScript — Code Generation Rules

Specific shapes the model must not write in TypeScript. Loaded **in addition** to `.claude/rules/javascript.md` — every JS rule applies to TS.

## Type escape hatches

- Never `as any`. If a value's type is genuinely unknown, use `unknown` and narrow with type guards.
- Never `as <type>` to silence an error you do not understand. Cast only when you have a runtime invariant that justifies it; add a same-line `// cast: <reason>` comment.
- Never `// @ts-ignore`. Use `// @ts-expect-error — <reason>` so the suppression is removed once the underlying issue is fixed.

## Strictness

- Never `// @ts-nocheck` in a file. If a file genuinely cannot be type-checked, exclude it in `tsconfig.json` with a comment in the config.
- Never declare a parameter or return type as `any`. Prefer `unknown` for untrusted inputs and narrow before use.

## Non-null assertion

- Avoid the `!` non-null assertion. Prefer narrowing (`if (value === undefined) throw …`) so the runtime check matches the type.

## Type narrowing

- Never type-guard with `obj.field === "x"` when the field is untyped externally. Validate inputs at the system boundary with a schema library (zod, valibot) and use the inferred type internally.

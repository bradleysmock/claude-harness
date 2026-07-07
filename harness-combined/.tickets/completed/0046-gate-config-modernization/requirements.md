# Requirements

**Ticket**: 0046
**Title**: Gate config modernization — respect project configs, ESLint flat config, current toolchain pins

## Functional Requirements

1. Directory-mode Python lint must run bare "ruff check ." (project config wins) when a
   ruff config exists (ruff.toml, .ruff.toml, or a tool.ruff table in pyproject.toml),
   and use the hardcoded select/ignore floor only when none exists.
2. Directory-mode mypy must run without --ignore-missing-imports; text mode retains the
   flag (temp dirs cannot resolve project imports).
3. TypeScript directory-mode lint must detect flat config (eslint.config.js/mjs/cjs/ts)
   and invoke eslint without the removed --ext flag in that case, keeping the legacy
   invocation only for legacy-config projects; text mode must ship a flat config and
   invoke eslint compatibly with v9 and later.
4. Text-mode environment pins must be raised to current stable: the Go go.mod
   directive, the Rust edition, and the TS target/module — each defined once as a
   named constant with a comment stating the review cadence.
5. When the host project root contains a go.mod, Cargo.toml, or tsconfig.json, text
   mode must prefer the host project's language/edition/target values over the
   constants.

## Non-Functional Requirements

1. No new runtime dependencies.
2. Gate behavior on projects without configs is unchanged apart from pin versions.

## Test Strategy

| Type        | Rationale                                                     |
|-------------|-----------------------------------------------------------------|
| Unit        | Config-detection branching for ruff, eslint flat vs legacy, pin overrides |
| Integration | Fixture projects: strict-ruff project surfaces its own rule hits; flat-config TS project lints cleanly |

## Acceptance Criteria

- On a fixture with tool.ruff selecting bugbear rules, the gate reports a bugbear
  violation the old hardcoded select missed.
- On a flat-config ESLint fixture, dir-mode lint passes with no TOOL_ERROR.
- Dir-mode mypy flags a nonexistent-module import on a fixture.
- Text-mode Go gate compiles a fixture using a post-1.21 language feature.

## Open Questions

- None.

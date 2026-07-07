# Solution

**Ticket**: 0046
**Title**: Gate config modernization — respect project configs, ESLint flat config, current toolchain pins

## Approach

Introduce config-detection helpers per language gate (has_ruff_config, eslint_config_kind,
host_toolchain_values) and branch invocations on them. Consolidate all text-mode pins
into named module constants with a documented review cadence, overridden by host-project
values when detectable.

## Components

| Component | Responsibility |
|-----------|----------------|
| gates/python.py | ruff config detection + bare invocation; dir-mode mypy flag removal |
| gates/typescript.py | eslint_config_kind (flat/legacy/none) branching; flat text-mode config; pin constants |
| gates/go.py, gates/rust.py | Pin constants + host go.mod / Cargo.toml value detection |
| tests + fixtures | Strict-ruff, flat-eslint, missing-import, modern-feature fixtures |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Project-config-wins with hardcoded floor | Never gate weaker than the project's own CI; keep a floor for bare projects |
| Detect config kind, not eslint version | Config files are on disk and cheap to check; version probing adds a subprocess |
| Named pin constants + host override | One place to bump; host detection removes most need to bump |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Integration | Strict-ruff fixture surfaces project-rule violation; bare fixture uses floor |
| FR-2 | Integration | Dir-mode mypy fails on missing-module fixture; text mode still passes it |
| FR-3 | Integration | Flat-config fixture lints without TOOL_ERROR; legacy fixture unchanged |
| FR-4 | Unit | Constants exist with cadence comment; no stale literals elsewhere |
| FR-5 | Unit | Host go.mod / Cargo.toml / tsconfig values override constants |

## Tradeoffs

- **Chose branching invocations over dual-running both configs because**: one correct
  invocation per project is predictable; dual runs double lint time for no signal.
- **Accepting risk of**: project configs weaker than the floor going undetected — a
  follow-up could diff project config against the floor and warn.

## Risks

- ESLint invocation differences across v8/v9/v10 — integration fixtures for both
  config kinds keep this honest.

## Implementation Order

1. Python: ruff config detection, mypy flag split, fixtures.
2. TypeScript: config-kind detection, flat text-mode config, drop --ext on flat.
3. Pin constants + host-value detection for go/rust/ts.
4. Full fixture matrix and regression run.

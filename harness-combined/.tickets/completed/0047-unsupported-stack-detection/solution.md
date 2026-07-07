# Solution

**Ticket**: 0047
**Title**: Honest handling of unsupported and mis-detected stacks

## Approach

Centralize detection in one helper set shared by server.py and reused conceptually by
the hook: marker-based stack detection with one-level-down parity across go/rust/ts, a
vendored-dir exclusion list, and an explicit unsupported result instead of a Python
default. The Stop hook gains a zero-stack warning branch.

## Components

| Component | Responsibility |
|-----------|----------------|
| server.py detection helpers | Parity markers, exclusion list, unsupported error result |
| gate_run_on_dir | Structured unsupported-stack error payload |
| hooks/stop_full_gate.py | Shared exclusion list; zero-stack stderr warning, exit 0 |
| tests + fixtures | Unsupported, subdir-go, vendored-python, zero-stack cases |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Explicit error over Python default | Fail honest; misleading tool errors cost diagnosis time |
| Bounded one-level glob + exclusions | Predictable cost; matches existing rust/ts convention |
| Duplicated small exclusion constant in hook | Hooks run standalone (no server import); keep both under one docs test |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit | Java-only fixture: auto mode returns unsupported error naming markers |
| FR-2 | Unit | api/go.mod fixture detected as Go stack |
| FR-3 | Unit | node_modules-only .py fixture not detected as Python (server and hook) |
| FR-4 | Unit | Zero-stack review-ready fixture: warning line, exit 0 |
| FR-5 | Unit | Explicit language callers unchanged for the four supported languages |

## Tradeoffs

- **Chose honest failure over best-effort Python gating because**: a wrong-language
  gate provides negative value — noise plus false confidence.
- **Accepting risk of**: breaking callers that relied on the Python default; the
  supported-language explicit path is preserved and tests pin it.

## Risks

- Exclusion list divergence between server and hook — guarded by a consistency test
  comparing the two constants.

## Implementation Order

1. Detection helpers + exclusion list in server.py; unsupported error path.
2. go.mod one-level parity.
3. Hook exclusions + zero-stack warning.
4. Fixture matrix; consistency test.

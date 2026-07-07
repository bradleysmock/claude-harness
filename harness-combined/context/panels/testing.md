## Testing Strategy Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md`. Where Core Dimension 7 reviews the **code quality** of individual tests, this panel reviews the **strategy** — what's tested, at what level, and how the suite holds together as a whole.*

- **Kent C. Dodds** — *Testing JavaScript*; the testing trophy, integration-over-unit bias, test-the-user-experience
- **Michael Feathers** — *Working Effectively with Legacy Code*; seams, test scaffolding, characterization tests, the unit-test pyramid critique

**Dodds's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The testing trophy, not the pyramid** | Static analysis at the base, then *integration* tests as the largest layer, then a thin layer of unit tests for hard-to-integration-test logic, then a smaller layer of E2E. Most bugs live at module boundaries — that's where tests should live. |
| **Test the way the user uses it** | A React component test that probes implementation (state, props, internal handlers) breaks on refactor and misses real bugs. Render it, interact with it the way a user would, assert on what they would see. `@testing-library` enforces this; flag tests that fight it. |
| **Mocking is debt** | Each mock is a claim about how the real thing behaves. The claim drifts. Mock at the external boundary (network, time, randomness, filesystem) — not at internal seams. |
| **A flaky test is a broken test** | Retry-until-green hides race conditions, async leaks, shared state. Quarantine and fix; never retry-and-ship. |
| **Coverage is a smoke detector, not a goal** | 100% coverage on getters proves nothing. 60% coverage on the auth flow with thoughtful edge cases is worth more. Look at *what* is covered, not the percentage. |

**Feathers's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **A seam is a place to alter behavior without editing the code** | Dependency injection, function parameters, interfaces — these are seams. Code without seams (static method chains, deep constructor coupling) is untestable without modification. |
| **Characterization tests pin down what code does, before changing it** | When working with legacy code, write tests that capture current behavior — even if that behavior is wrong — before refactoring. The tests then catch unintended changes. |
| **Tests are the documentation of intent** | If a behavior isn't tested, it isn't specified — future readers don't know if it's a feature or an accident. Test the surprising behaviors explicitly. |
| **Beware the integration-only suite** | All-integration suites with no unit tests catch breakage but localize nothing — every failure points at "the whole pipeline." Unit tests at well-chosen seams give a fault address. |
| **Slow tests don't get run** | A test suite that takes 20 minutes runs once per push. A 90-second suite runs every save. Optimize for the cadence you want. |

*Synthesis:* Dodds and Feathers largely agree on the modern shape (more integration, less unit-of-implementation), but tension exists: Dodds is more willing to skip the unit layer entirely for typical app code; Feathers insists on unit tests at carefully-chosen seams for diagnosability. The synthesis: integration tests are the default; unit tests are deliberate — added where the seam reveals a class of error worth pinning.

---

## Review Dimensions

---

### Dimension 22: Test Strategy & Suite Shape
*Dodds, Feathers*

| Hazard | What to look for |
|--------|-----------------|
| **Inverted trophy** | Hundreds of unit tests, almost no integration tests. Refactors break dozens of tests without any production bug being caught. |
| **Mocks at internal seams** | Tests that mock a module the system under test depends on directly — couples the test to implementation. Mock at the external boundary (HTTP, DB, time, random, fs). |
| **Tests probing implementation** | React tests inspecting `state`, `props`, or internal handler names. Backend tests asserting on private method calls. Behavior should be observable from the outside. |
| **Untested critical paths** | Auth, payment, data export, permission enforcement — flows where failure is irrecoverable — without integration tests covering the unhappy paths. |
| **Flaky tests retried** | CI config with `retries: 3` on a test suite. Hides race conditions; trains developers to ignore failures. |
| **No test isolation** | Tests that depend on execution order, share global state, or leak fixtures across files. Parallelism becomes unsafe. |
| **Fixtures over factories** | Static fixture files (`tests/fixtures/user.json`) for objects that need variation. Every test reuses the same shape; edge cases go untested. Use factory functions with overrides. |
| **No seams in production code** | New code with no way to substitute dependencies — direct imports of clients, hardcoded `new` calls, static singletons. Tests must reach for the network or skip the path. |
| **Snapshot tests as a default** | `expect(...).toMatchSnapshot()` for anything beyond stable serializable output. Snapshots get updated mechanically and stop catching regressions. |
| **No characterization tests before refactor** | A behavior-changing refactor of untested legacy code with no tests added in the same change to capture pre-change behavior. |
| **Test setup duplication** | The same 15 lines of arrange-code at the top of 40 tests. Extract a builder or factory; the duplication hides what each test actually varies. |
| **Slow CI suite without parallelization** | A 20-minute test job that could shard across runners. Long feedback cycles → tests get bypassed. |
| **Production-only branches** | `if (process.env.NODE_ENV === 'production')` paths with no test coverage. These only execute where you have the least ability to debug. |
| **Tests asserting on log/console output** | Tests verifying behavior via captured stdout — couples to log format. Assert on the observable return value, side effect, or persisted state. |
| **`it.skip` / `xfail` / `t.Skip` without a tracked reason** | Skipped tests in the suite with no comment linking to an issue or explaining the temporary condition. Skips become permanent. |
| **Tests using real wall-clock or real network** | `sleep(2)` or actual HTTP calls inside unit/integration tests — slow, flaky, and dependent on external state. Use a clock abstraction and an HTTP mocking layer. |

Feathers's design question: if a junior engineer changed the behavior of a function in this codebase by accident, which test would fail, and would the failure message point them to the change?

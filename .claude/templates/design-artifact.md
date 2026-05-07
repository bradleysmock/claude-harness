# Design Artifact

**Component:** [Component name]
**Date:** [YYYY-MM-DD]
**Pipeline Stage:** 2 — Design Synthesis
**Specification:** `pipeline/spec.yaml`

---

## 1. Public Interface Definition

[Define every public function, method, class, or endpoint.]

### [Interface Element 1]

```python
# Example (adapt to target language)
def function_name(
    param1: Type1,
    param2: Type2,
    *,
    optional_param: Type3 | None = None,
) -> ReturnType:
    """One-line summary.

    Args:
        param1: Description and constraints.
        param2: Description and constraints.
        optional_param: Description. Defaults to None.

    Returns:
        Description of what is returned and when.

    Raises:
        SpecificError: When [condition].
        AnotherError: When [condition].
    """
```

**Preconditions:**
- [Condition that must hold before calling]

**Postconditions:**
- [Guarantee that holds after a successful call]

**Side effects:**
- [Any I/O, external calls, or state mutations]

---

## 2. Data Model

### [Entity 1]

| Field | Type | Nullable | Constraints | Description |
|-------|------|----------|-------------|-------------|
| id | UUID | No | Unique | Primary identifier |
| [field] | [type] | [Y/N] | [constraints] | [description] |

### [Entity 2]

[...]

---

## 3. Dependency Manifest

| Package | Version | Purpose | Alternative Considered | License |
|---------|---------|---------|----------------------|---------|
| [name] | [pinned] | [one sentence] | [alternative + reason rejected] | [license] |

**CVE scan result:** [CLEAN / list any findings]

---

## 4. Module Dependency Graph

```
[Component Name]
├── depends on: [module A]
├── depends on: [module B]
│   └── depends on: [module C]
└── exposes to: [consumer D]
```

**Circular dependency check:** [NONE DETECTED / list any found and resolution]

---

## 5. Architectural Decision Record

See `pipeline/adr.md`

---

## 6. Test Plan

| Criterion ID | Test Case Name | Test Type | Inputs | Expected Output | Edge Cases |
|-------------|---------------|-----------|--------|-----------------|------------|
| AC-01 | test_[what]_[when]_[then] | unit | [values] | [outcome] | [edge cases] |
| AC-02 | test_[what]_[when]_[then] | unit | [values] | [outcome] | [edge cases] |
| AC-01 | test_[error_scenario] | unit | [invalid input] | [error type + message] | — |
| AC-N | test_[integration_scenario] | integration | [setup + action] | [end-to-end outcome] | [concurrent, timeout] |

**Total test cases:** [N]
**Coverage of acceptance criteria:** [N/N]

---

## 7. Security Review

**Classification:** [PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED]
**High-risk patterns:** [NONE / list patterns found]

[If high-risk patterns found:]

### Security Review Required

The following patterns require elevated scrutiny:

- **[Pattern 1]:** [Why it is high-risk and what specific controls are needed]
- **[Pattern 2]:** [...]

**Required controls to implement:**
- [ ] [Control 1]
- [ ] [Control 2]

**Reviewer required:** [Named reviewer if CONFIDENTIAL/RESTRICTED]

---

*This design artifact is the authoritative contract for Stage 3 code generation.*
*Do not modify it after Stage 3 begins without re-running the full pipeline.*

# Design: [Task Name]

> Produced by `/design`. This file is the single source of truth for what to build.
> Get human approval before running `/build`.

---

## Problem

What needs to be built and why. Include:
- The specific capability or change required
- Why it's needed (user need, bug, business requirement)
- Success criteria — how to know when it's done

---

## Approach

High-level implementation strategy:
- Module structure and responsibilities
- Key patterns and libraries
- What is explicitly out of scope

---

## Interface Contracts

All public-facing interfaces defined before implementation begins.

### API Endpoints (if applicable)

```
METHOD /path
  Request:  { field: type }
  Response: { field: type }
  Errors:   { code: number, message: string }
```

### Functions / Classes

```
functionName(param: Type): ReturnType
  Precondition: ...
  Postcondition: ...
  Errors: ...
```

### Data Schemas

```
TypeName {
  field: type  // constraints
}
```

---

## Decisions

One entry per meaningful design choice. Be specific about what was rejected and why — this is the most valuable section for future readers.

**Decision**: [what was decided]
**Rejected**: [alternatives considered and why they lost]
**Consequence**: [what this commits to or defers]

---

## Test Plan

| Acceptance Criterion | Test Case | Type | Expected Result |
|----------------------|-----------|------|-----------------|
| | | unit / integration / e2e | |

---

## Risk Flags

<!-- High-risk patterns detected by /design are listed here -->
<!-- auth, crypto, PII handling, payment → require human review before /build -->

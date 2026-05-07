# Specification Writing Guide

The quality of your specification is the single largest determinant of output quality. This guide explains how to write specifications that consistently achieve Gate 1 scores of 9–10/10.

---

## The Specification Scoring Rubric

| Dimension | Points | What earns full marks |
|-----------|--------|----------------------|
| Task clarity | 1 | Single imperative sentence, no ambiguity |
| Functional completeness | 2 | ≥5 requirements covering all paths |
| NFR measurability | 2 | Every NFR has a numeric threshold |
| Context richness | 1 | Relevant interfaces/schemas provided |
| Security classification | 1 | Declared with data types named |
| Acceptance criteria | 2 | ≥3 criteria, all binary and testable |
| Edge case coverage | 1 | At least 1 error/boundary scenario |

---

## Common Rejection Reasons

### ❌ Unquantified NFRs

Bad:
```yaml
non_functional_requirements:
  - "The service should be fast"
  - "Must handle high load"
  - "Should be secure"
```

Good:
```yaml
non_functional_requirements:
  - "p99 response time must be < 200ms under 500 concurrent users (measured via k6)"
  - "Must sustain 10,000 requests/minute without degradation for 30 minutes"
  - "All inputs must be validated against a schema; invalid inputs return 400 within 10ms"
```

---

### ❌ Vague functional requirements

Bad:
```yaml
functional_requirements:
  - "Process user data"
  - "Handle errors appropriately"
  - "Should be scalable"
```

Good:
```yaml
functional_requirements:
  - "Accepts a UserRegistration payload and creates a new User record in the database"
  - "Validates that the email field is a valid RFC 5322 address; rejects with 422 and field-level error if invalid"
  - "Returns 409 Conflict if a user with the same email already exists"
  - "Hashes the password using bcrypt with cost factor 12 before persisting"
  - "Emits a UserRegistered domain event after successful persistence"
```

---

### ❌ Untestable acceptance criteria

Bad:
```yaml
acceptance_criteria:
  - "The system works correctly"
  - "Users can register"
  - "Errors are handled well"
```

Good:
```yaml
acceptance_criteria:
  - |
    Given: A POST /users request with a valid email, strong password, and display name
    When:  The request is processed
    Then:  A 201 response is returned with the new user's ID and a confirmation email is queued
  - |
    Given: A POST /users request with a malformed email address
    When:  The request is processed
    Then:  A 422 response is returned with a body containing {"field": "email", "error": "invalid_format"}
  - |
    Given: A POST /users request where the email matches an existing user
    When:  The request is processed
    Then:  A 409 response is returned with body {"error": "email_already_registered"}
```

---

## Checklist Before Running /intake

Work through this list before submitting your spec:

**Task statement:**
- [ ] Describes a single component (not a system)
- [ ] Uses a specific verb (not "handle", "manage", "deal with")
- [ ] Has no vague qualifiers

**Functional requirements:**
- [ ] ≥5 requirements
- [ ] Each starts with an action verb (Accepts, Returns, Validates, Rejects, Emits, Stores...)
- [ ] Happy path covered by ≥2 requirements
- [ ] Error paths covered by ≥2 requirements
- [ ] No requirement contains "fast", "secure", "appropriate", or similar

**NFRs:**
- [ ] Every NFR has a number (ms, %, MB, req/s, users...)
- [ ] Performance NFRs specify the load level ("at 500 concurrent users")
- [ ] Availability NFRs specify the measurement period

**Codebase context:**
- [ ] Relevant interfaces, types, or schemas are included
- [ ] Context is ≤ ~4,000 tokens

**Security classification:**
- [ ] One of: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED
- [ ] Data types processed are named explicitly

**Acceptance criteria:**
- [ ] ≥3 criteria
- [ ] Each uses Given/When/Then or assert/verify/expect form
- [ ] Each is binary (pass/fail, not "somewhat satisfies")
- [ ] Error scenarios are included alongside success scenarios
- [ ] Edge cases covered (empty inputs, max values, concurrent calls)

---

## Example: A Well-Specified Component

```yaml
task_statement: >
  Implement a JWT authentication middleware that validates Bearer tokens,
  extracts the user identity, and attaches it to the request context
  for downstream handlers.

functional_requirements:
  - Extracts the Authorization header from incoming HTTP requests
  - Validates that the header value matches the pattern "Bearer <token>"
  - Verifies the JWT signature using RS256 with the configured public key
  - Rejects tokens that are expired, malformed, or signed with an unknown key
  - Attaches a validated UserPrincipal object to the request context on success
  - Returns 401 Unauthorized for all authentication failures without revealing the failure reason to the caller

non_functional_requirements:
  - Validation must complete in < 5ms at p99 (excluding network I/O)
  - Must not cache or store JWT tokens; verification is stateless
  - Must support token rotation with a configurable 60-second grace period for clock skew
  - Public key must be loaded from environment variable, not from code

target_language:
  language: python
  version: ">=3.11"
  runtime: "ASGI (FastAPI)"
  framework: "FastAPI 0.115"

codebase_context: |
  # Existing request context protocol
  class RequestContext(Protocol):
      def set_principal(self, principal: UserPrincipal) -> None: ...
      def get_principal(self) -> UserPrincipal | None: ...

  # UserPrincipal value object
  @dataclass(frozen=True)
  class UserPrincipal:
      user_id: UUID
      roles: frozenset[str]
      issued_at: datetime

security_classification: CONFIDENTIAL
data_types_processed:
  - "JWT tokens containing user identity and role claims"
  - "RSA public key for signature verification"

acceptance_criteria:
  - |
    Given: A request with Authorization: Bearer <valid_signed_jwt>
    When:  The middleware processes the request
    Then:  The handler receives the request with a populated UserPrincipal in context
  - |
    Given: A request with an expired JWT (exp claim < now)
    When:  The middleware processes the request
    Then:  A 401 response is returned; the handler is never called; no JWT details in response body
  - |
    Given: A request with no Authorization header
    When:  The middleware processes the request
    Then:  A 401 response is returned with WWW-Authenticate: Bearer in the response headers
  - |
    Given: A JWT signed with an unknown private key
    When:  The middleware processes the request
    Then:  A 401 response is returned; the signature error is logged internally but not returned to the caller
```

This specification scores 10/10 and will produce high-quality, first-pass-approved output.

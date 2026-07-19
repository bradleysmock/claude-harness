## Core Panel

*Always active — the trigger table in `context/panels/triggers.md` loads Core for every file in scope; that table is the single activation source.*

- **Robert C. Martin** — *Clean Code*, *The Clean Coder*
- **David Parnas** — *On the Criteria To Be Used in Decomposing Systems into Modules* (1972); the canonical source on information hiding and module decomposition
- **John Ousterhout** — *A Philosophy of Software Design*
- **Martin Fowler** — *Refactoring*, *Patterns of Enterprise Application Architecture*
- **Kent Beck** — *Test-Driven Development*, *Implementation Patterns*
- **Gary McGraw** — *Software Security: Building Security In*
- **Eric Evans** — *Domain-Driven Design*

Martin, Ousterhout, Fowler, and Beck disagree on design questions. Where they diverge, weigh the merits and deliver a synthesized verdict. Do not dogmatically apply any single expert's rules. Parnas's information-hiding principle is the foundation Ousterhout's "deep modules" argument rests on — cite Parnas where the question is *what* should be hidden, Ousterhout where the question is *how the interface should be shaped*. McGraw and Evans apply orthogonal lenses that do not compete — apply them in addition to the design review. A finding from McGraw or Evans is a BLOCKER if it is a design-level flaw.

---

## Expert Positions Reference

### On Function/Method Size

| Expert | Position |
|--------|----------|
| **Martin** | Functions should be tiny—ideally 2–4 lines. If you can extract a method with a meaningful name, you should. |
| **Ousterhout** | Extreme decomposition creates entanglement: readers must jump between methods and reconstruct context. Prefer deep modules — small interfaces hiding substantial complexity — over shallow ones. |
| **Fowler** | *Extract Method* is the most valuable refactoring, but only when the extracted piece has independent meaning. Fragmented code is a smell in its own right. |

**Synthesis:** Extract when (a) the extracted unit has standalone meaning a reader can grasp without surrounding context, AND (b) the call site is cleaner for the extraction. Test: replace the function body with just its name at the call site — does the caller make more sense? If yes, extract. If the reader must still look at the body to understand the caller, reconsider.

---

### On Comments

| Expert | Position |
|--------|----------|
| **Martin** | Comments are failures to express intent in code. The best comment is the one you didn't need to write. |
| **Ousterhout** | Comments are essential. Two legitimate uses: (1) documenting what an abstraction does and why it was designed this way; (2) explaining non-obvious information that cannot be encoded in a name. |
| **Fowler** | Comments that explain *why*, not *what*, are almost always valuable. Comments that narrate code are noise. |

**Synthesis:** Three-way test: interface/API documentation → write it; why-comments (surprising decisions, rejected alternatives) → write them; what-comments (narrating what the code clearly says) → remove them.

---

### On Naming

| Expert | Position |
|--------|----------|
| **Martin** | Scope-based: smaller scope, longer name acceptable. Long names are harder to ignore than comments. |
| **Ousterhout** | Names should be precise, not exhaustive. Megasyllabic names are cognitive burden. |
| **Fowler** | Names should reveal intent. Avoid vague words: Manager, Handler, Data, Info, Processor. Rename relentlessly. |

**Synthesis:** Precision is the goal, not length. Avoid vague nouns regardless of length. Prefer a shorter, precise name + an interface comment to a name that attempts to encode the full specification.

---

### On Security (McGraw)

| McGraw's Position | What it means in practice |
|-------------------|-----------------------------|
| **Bugs vs. flaws** | Security *bugs* are implementation errors; security *flaws* are design errors (wrong trust boundary, authorization at the wrong layer). Flaws are BLOCKERs — you cannot patch your way out of a wrong trust boundary. |
| **Think like an attacker** | For every external input: what can a malicious actor supply, and what does the code do with it? Walk the threat model, not just the happy path. |
| **Minimize attack surface** | Every public route, every accepted parameter, every trusted header is a potential attack vector. The thing not exposed cannot be exploited. |
| **Fail closed** | A failed security check, a missing config value, an unhandled exception in an authz code path — should all deny access. The default for ambiguity is "no." |
| **Defense in depth** | Validation at the route layer is good; validation at the service layer as well is better; database constraints as a third layer make exploitation require breaking three things in sequence. |
| **Trust no input across a boundary** | Every value crossing a trust boundary needs validation — structure, type, length, value, and *meaning*. Trust boundaries: external user → process, network → process, file → process, model → process, process → process across a privilege gap. Validation at the consumer is necessary, not sufficient — validate at the boundary itself. |
| **Validate semantics, not just syntax** | A path that parses cleanly may still escape your sandbox. A URL that parses may resolve to an internal address (SSRF). A username that's valid UTF-8 may exploit Unicode normalization. Syntax checks catch the obviously-malformed; semantic checks catch the well-formed-but-malicious. |
| **Logs are a security perimeter** | Telemetry destinations have their own access model, retention, and breach surface. PII, secrets, session tokens, full request bodies in logs multiply the surface where a single log-store breach is consequential. The log destination is not "internal" — treat it as another consumer with its own trust level. |
| **The error response is part of the response** | Stack traces, library versions, file paths, internal hostnames, ORM details in production error responses are free reconnaissance. The operator-facing diagnostic and the user-facing message should be different artifacts produced by different code paths. |
| **Time and timing carry information** | Comparison short-circuits on `==`, password-verification loops that exit on first byte mismatch, response-time differences across "does this user exist" probes all leak through side channels. Use constant-time comparison for any secret-vs-input check; equalize response time for endpoints whose existence leaks should be prevented. |
| **Trust decay over time** | A capability granted today (an API key, a session, a cached authorization decision, a privileged container) accumulates exposure with every day it remains valid. Expire, rotate, and reauthorize on a schedule. Long-lived credentials and "temporary" sudoes that became permanent are the recurring incident pattern. |

---

### On Simple Design (Beck)

| Rule | Priority | What to look for |
|------|----------|-----------------|
| **Passes tests** | 1 | Correctness is non-negotiable. |
| **Reveals intention** | 2 | Names, structure, and decomposition communicate what the code does. |
| **No duplication** | 3 | Not just literal copy-paste — also duplication of *knowledge* (same business rule in two places). |
| **Fewest elements** | 4 | Remove everything not required by rules 1–3. No speculative abstractions. |

---

### On Decomposition & Cognitive Load

| Expert | Position |
|--------|----------|
| **Martin** | Small units are easier to test, name, and reason about. Single Responsibility Principle. |
| **Ousterhout** | Complexity is a function of information a developer must hold in mind simultaneously. Decomposition that increases entanglement increases complexity. |
| **Fowler** | Identify and eliminate code smells: Feature Envy, Inappropriate Intimacy, Shotgun Surgery, Divergent Change. |

**Synthesis:** Decompose along boundaries that *reduce* information load. A good decomposition means a reader can understand module A without reading module B.

---

### On Information Hiding (Parnas, Ousterhout)

Parnas's 1972 question — *what should be hidden inside a module so that callers do not depend on it* — predates and underwrites most modern design advice on this topic. Ousterhout's "deep modules" argument is a restatement: a deep module hides a lot of complexity behind a small interface, which is only achievable if you correctly identified *what to hide*.

| Question | Test |
|---|---|
| **What is likely to change?** | Encapsulate the changing part. The most stable interface hides the least stable implementation. If a design decision could plausibly be revisited, hide it behind an interface that won't have to. |
| **Could a caller reasonably depend on this?** | If yes, it is API — even if the keyword says `private`, even if the docs say "internal." See Hyrum's Law below. The mitigation is to narrow the *observable* surface, not to wish callers behaved better. |
| **Does the interface leak implementation choices?** | Returning ORM model instances, framework-specific exception types, connection-pool objects, library-specific iterators — each makes the underlying choice part of the contract. Wrap or translate at the boundary. |
| **Could two competent implementations satisfy this interface?** | If the answer is no, the interface is over-specified — it has encoded one implementation's shape as part of its contract. |

---

### On Public APIs & Hyrum's Law (Wright)

**Hyrum's Law (Hyrum Wright, Google):** *With a sufficient number of users of an API, it does not matter what you promise in the contract: all observable behaviors of your system will be depended on by somebody.*

This is not a moral failing of users — it is a statistical property of large systems. Defensive implications:

- **"Internal" behaviors leaked through public surfaces become contracts** whether you intended them to or not. Error message strings, the order of results in a "set," timing characteristics, JSON field ordering, default value choices, log format — all are observable and therefore depended upon.
- **Refactors that change observable behavior are breaking changes** even when the documented contract is unchanged. "We didn't promise that" is true and irrelevant when monitoring dashboards, downstream consumers, and tests start failing.
- **The mitigation is narrowing observable surface, not stricter docs.** Hide what shouldn't be depended on (Parnas above). For surface you can't narrow, treat changes to it as semver-significant.
- **Progressive deprecation when reducing surface.** Add the new shape; instrument calls to the old shape; communicate; sunset only when usage reaches zero or an acceptable floor.

Hyrum's Law applies most strongly to: public library APIs, public HTTP APIs (overlap with HTTP/API panel), exported type definitions, error types and messages, and any function whose return-value structure, ordering, or side-effect timing is observable across a process or team boundary.

---

### On Domain Modeling (Evans)

| Pattern | What to look for |
|---------|--------------------|
| **Ubiquitous language** | Code vocabulary matches the domain's spoken language. |
| **Entities vs value objects** | Entities have identity (compared by ID); value objects are immutable and compared by value. |
| **Aggregate invariants** | Changes to a cluster of objects go through the aggregate root. Flag direct modification of inner objects. |
| **Domain logic placement** | Business logic belongs in services/entities, not scattered across route handlers. |
| **Implicit domain events** | Significant state changes should be named events, not silent side effects inside methods. |

---

## Review Dimensions

Read all files in scope first. Then produce findings across every applicable dimension.

---

### Dimension 1: Abstraction Quality
*Ousterhout, Fowler*

- Are modules deep (simple interfaces hiding significant complexity) or shallow (thin wrappers)?
- Do abstractions leak implementation details through their interfaces?
- Are there pass-through methods that add no value? (Fowler: Middle Man)
- Do abstractions at the same layer represent the same level of generality?

---

### Dimension 2: Decomposition & Entanglement
*Martin, Ousterhout synthesis*

- Entanglement test: does understanding any method require reading others to reconstruct context?
- Are there shallow extracted methods — single-line wrappers — that add indirection without adding meaning?
- Are related pieces of logic split when they share state and should be read together?
- "And" test (Fowler/Martin): if you can't describe a function without saying "and," it has multiple responsibilities.

---

### Dimension 3: Naming Precision
*All three*

- Are names precise? Do they convey exactly what the entity is without requiring the reader to check the implementation?
- Vague nouns: Manager, Handler, Helper, Util, Data, Info, Processor?
- Misleading names? Boolean names unambiguous? Collection names reflect element type?

---

### Dimension 4: Documentation & Comments
*Ousterhout, Fowler, Martin*

Apply the three-way test: interfaces → document; why-comments → write; what-comments → remove.

- Is the contract documented for every public function? Preconditions, return value, errors?
- Is the documentation accurate? (Stale comments are worse than none.)
- Are there non-obvious decisions explained? Rejected alternatives?
- Are there TODO comments without tracking references?

---

### Dimension 5: Code Smells
*Fowler, Martin, Beck*

Flag only where there is actual evidence:

| Smell | Indicator |
|-------|-----------|
| Long Method | Multiple abstraction levels mixed |
| Large Class | "And" appears in its description |
| Feature Envy | Method more interested in another class's data |
| Data Clumps | Parameters that always appear together → introduce an object |
| Primitive Obsession | Raw strings/ints where a domain type adds safety |
| Lazy Class | Doesn't justify its existence |
| Speculative Generality | Abstractions for imagined future requirements (Beck rule 4) |
| Temporary Field | Fields only set in some states |
| Inappropriate Intimacy | Classes that know too much about each other's internals |
| Shotgun Surgery | One logical change requires edits in many places |

---

### Dimension 6: Design Principles
*Martin (SOLID), Parnas, Ousterhout, Wright (Hyrum's Law)*

Apply only where clearly evidenced:

- **SRP**: one reason to change?
- **OCP**: new behaviors without modifying existing code?
- **DIP**: higher-level modules depend on abstractions, not concretions?
- **Information Hiding (Parnas)**: would a change to the implementation require changes to callers? If yes, the boundary is in the wrong place — the implementation choice is part of the interface.
- **Hyrum's Law surface**: for any public-ish API in this change, what observable behaviors beyond the documented contract are callers able to depend on? Error message strings, ordering, timing, side-effect order, log format. Each is a future-breaking-change waiting to happen if not deliberately narrowed.

---

### Dimension 7: Test Quality
*Fowler, Martin, Beck*

- Do tests verify **behavior** or **implementation**?
- Are mocks limited to the external boundary (I/O, network, time)?
- Are tests independent, deterministic?
- Edge cases: empty inputs, nulls, error paths, concurrent access?
- Beck: does the test read like a specification? Can you understand what the system does from the test alone?

---

### Dimension 8: Security
*McGraw*

| Class | What to look for |
|-------|-----------------|
| Path traversal | User input in file path construction without `.resolve()` + `relative_to()` containment check against an allowed root. |
| Command injection | User input to `subprocess`, especially `shell=True` or string interpolation. Pass argument lists; never assemble shell strings. |
| SQL injection | String-interpolated SQL with any value not authored by you. Use parameter binding without exception, including for table names (via allow-list) and `ORDER BY` columns. |
| Server-side template injection | User input rendered through a template engine (Jinja2, Handlebars, Liquid) as *template source*, not as *template data*. The two are different APIs; mixing them is RCE. |
| Insecure deserialization | `pickle.loads`, `yaml.load` without `SafeLoader`, Java `ObjectInputStream`, PHP `unserialize`, JS `node-serialize` on any value you did not author yourself. Each is RCE. |
| XML External Entity (XXE) | XML parsing with external entity resolution enabled — `lxml`, `xml.etree`, `DocumentBuilderFactory` defaults. Disable DTD/entity processing on every parser. |
| SSRF | Server fetching a user-supplied URL without an allow-list of destinations. Beware metadata endpoints (`169.254.169.254`), `localhost`, RFC1918 ranges, DNS rebinding. |
| Input validation gaps | Untrusted data reaching filesystem, subprocess, data store, network, or model context without structure / type / length / value / semantic validation at the boundary. |
| Mass assignment / IDOR | Object-level identifiers from request body accepted without an authorization check that the caller may operate on that object. Framework "model.update(request_body)" idioms are the canonical foothold. |
| ReDoS | Regex with catastrophic backtracking (`(a+)+`, `(.*)*`, nested quantifiers over user input). Either constrain input length pre-match or use a non-backtracking engine (Go `regexp`, Rust `regex`). |
| Timing attack on secrets | Plain `==` comparison of tokens, password hashes, HMACs. Use `hmac.compare_digest`, `crypto.timingSafeEqual`, equivalent. |
| Information leakage | Stack traces, internal paths, library versions, hostnames, or secrets in HTTP/RPC error responses. Operator and user diagnostics are different artifacts. |
| Hardcoded secrets | API keys, passwords, tokens in source, config, fixtures, test data, or commit history. |
| Secrets / PII in logs | Authorization headers, session tokens, API keys, user PII flowing into telemetry via wholesale request/response dumps or naive `logger.info(obj)`. |
| Authentication / authorization bypass | Routes missing auth; authorization delegated to client-supplied values (`X-User-Id`, JWT `sub` accepted without signature verification); permission checks at the wrong layer. |
| Missing CSRF protection | State-mutating endpoint accepting cookie-authenticated requests without a CSRF token, SameSite cookie discipline, or proof-of-intent header check. |
| Cookie flags missing | Session / auth cookies without `HttpOnly`, `Secure`, `SameSite=Lax` (or stricter). Each missing flag is a class of exploit reopened. |
| Session fixation | Login flow that does not regenerate the session identifier on authentication. Attacker-supplied session ID persists post-login. |
| TOCTOU races | Check-then-use with a resource that can change between check and use (file existence then open, user-quota check then write). Capture state once or use atomic operations. |
| Open redirect | User-controlled values in `Location`, `HX-Redirect`, or framework redirect helpers without same-origin or allow-list enforcement. |
| Prototype pollution (JS) | `Object.assign(target, untrusted)`, recursive merge of user JSON, lodash `_.set` with user-controlled key path. Reaches `__proto__` and corrupts cross-application state. |
| Long-lived credentials | API keys, service-account tokens, signed URLs with no rotation schedule, no expiry, no audit trail. Trust decays; credentials that don't decay accumulate exposure. |

Design-level questions: are trust boundaries correct and minimal? Is authorization enforced server-side for every state-mutating action, at every layer that can be entered? Does the code fail closed on every error path in security-relevant code? For every secret in this codebase, what is its rotation policy and where is it actually stored?

---

### Dimension 9: Domain Modeling
*Evans*

- Does code vocabulary match the domain's spoken language?
- Are entities compared by identity, value objects by value?
- Are aggregate invariants enforced through the aggregate root?
- Is domain logic in the domain layer, not scattered across routes?
- Are significant state changes named events rather than silent side effects?

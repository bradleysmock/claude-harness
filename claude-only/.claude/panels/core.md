## Core Panel

*Always active.*

- **Robert C. Martin** — *Clean Code*, *The Clean Coder*
- **John Ousterhout** — *A Philosophy of Software Design*
- **Martin Fowler** — *Refactoring*, *Patterns of Enterprise Application Architecture*
- **Kent Beck** — *Test-Driven Development*, *Implementation Patterns*
- **Gary McGraw** — *Software Security: Building Security In*
- **Eric Evans** — *Domain-Driven Design*

Martin, Ousterhout, Fowler, and Beck disagree on design questions. Where they diverge, weigh the merits and deliver a synthesized verdict. Do not dogmatically apply any single expert's rules. McGraw and Evans apply orthogonal lenses that do not compete — apply them in addition to the design review. A finding from McGraw or Evans is a BLOCKER if it is a design-level flaw.

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
| **Bugs vs. flaws** | Security *bugs* are implementation errors; security *flaws* are design errors (wrong trust boundary, authorization at the wrong layer). Flaws are BLOCKERs. |
| **Think like an attacker** | For every external input: what can a malicious actor supply, and what does the code do with it? |
| **Minimize attack surface** | Every public route, every accepted parameter, every trusted header is a potential attack vector. |
| **Fail closed** | A failed security check should deny access by default. |
| **Defense in depth** | Validation at the route layer is good; validation at the service layer as well is better. |

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
*Martin (SOLID), Ousterhout*

Apply only where clearly evidenced:

- **SRP**: one reason to change?
- **OCP**: new behaviors without modifying existing code?
- **DIP**: higher-level modules depend on abstractions, not concretions?
- **Information Hiding**: would a change to the implementation require changes to callers?

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
| Path traversal | User input in file path construction without `.resolve()` + `relative_to()` |
| Command injection | User input to `subprocess`, especially `shell=True` or string interpolation |
| Input validation gaps | Untrusted data reaching filesystem, subprocess, or data store without validation |
| Information leakage | Stack traces, internal paths, or secrets in HTTP responses |
| Hardcoded secrets | API keys, passwords, tokens in source or config |
| Authentication/authorization bypass | Routes missing auth; authorization delegated to client-supplied values |
| TOCTOU races | Check-then-use with resource that can change between check and use |
| Open redirect | User-controlled values in `HX-Redirect` or `Location` headers without same-origin restriction |

Design-level questions: are trust boundaries correct? Is authorization server-side for every state-mutating action? Does the code fail closed?

---

### Dimension 9: Domain Modeling
*Evans*

- Does code vocabulary match the domain's spoken language?
- Are entities compared by identity, value objects by value?
- Are aggregate invariants enforced through the aggregate root?
- Is domain logic in the domain layer, not scattered across routes?
- Are significant state changes named events rather than silent side effects?

# Expert Code Critique

You are conducting a structured expert critique. Read every file in scope before writing a single finding. The output covers two scopes: **this change** (findings specific to the changed files) and **codebase patterns** (what this change reveals about systemic habits, good or bad, across the broader codebase).

---

## Panel Assembly

Before reading any code, determine which panels apply based on the files in scope. Announce the active panels.

| Files in scope | Panels to consult | Dimensions |
|----------------|-------------------|------------|
| Any file | **Core** | 1–9 |
| `app/**/*.py`, `tests/**/*.py` | **Python** | 10–11 |
| `app/routes/**` | **HTTP/API** | 12 |
| `app/templates/**`, `app/static/**` | **UI** | 13–14 |
| `app/clients/**` or any LLM invocation | **AI/LLM** | 15 |

Panels are additive. A route file (`app/routes/sessions.py`) activates Core + Python + HTTP/API. A template file activates Core + UI. A service file activates Core + Python.

---

## Target

```
$ARGUMENTS
```

If `$ARGUMENTS` is empty, review all changed files (per `git diff --name-only`). If a specific file or glob is given, review those files. Read every file in scope before writing a single finding.

---

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

## Python Panel

*Active when `app/**/*.py` or `tests/**/*.py` files are in scope.*

- **Raymond Hettinger** — CPython core developer; idiomatic Python, stdlib-first design
- **David Beazley** — *Python Cookbook*, *Python Essential Reference*; Python internals, asyncio architecture, coroutine lifecycle, CPython execution model

Beazley's positions complement Hettinger's idiom focus with a deeper machinery lens. Where Hettinger asks "is there a stdlib primitive for this?", Beazley asks "does this correctly model how Python's async machinery actually works?"

**Beazley's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **Understand the event loop** | asyncio is not threads. The event loop runs one coroutine at a time; `await` is a voluntary yield. Code written as if coroutines run in parallel (without `await` separating them) is correct by accident. Code with compound operations across `await` is a race waiting to be noticed. |
| **`asyncio.to_thread` is a thread boundary** | Objects passed into or out of `asyncio.to_thread` cross from the event loop's single-threaded world into a real thread. They need locking or must be immutable. The return value is awaited back in the event loop — it's safe. The arguments are not. |
| **Generator protocol underlies everything** | `async def` functions are generators that yield `Future` objects. Understanding this resolves many "why does this behave unexpectedly" questions: cancellation, exception propagation through `await`, and why `asyncio.CancelledError` should not be caught silently. |
| **Task cancellation must be handled** | An `asyncio.Task` cancelled while awaiting will raise `CancelledError` at the `await` point. Code that catches broad exceptions (`except Exception`) without re-raising `CancelledError` is broken — cancellation propagation stops and the task appears to hang. |
| **`asyncio.gather` failure semantics** | When one coroutine in `gather` raises, the others are not cancelled by default. If the caller doesn't handle this, partially-completed operations can leave state inconsistent. Use `return_exceptions=True` deliberately, or use a `TaskGroup`. |

*Synthesis with Hettinger:* Hettinger's idioms apply to async code too — use `async for`, `async with`, `anyio`/`asyncio` primitives over manual coroutine management. But Beazley's machinery understanding is the lens that catches the subtle correctness bugs idiom can't surface.

---

## HTTP/API Panel

*Active when `app/routes/**` files are in scope.*

- **Carson Gross** — creator of HTMX; *Hypermedia Systems* (with Adam Stepinski and Deniz Akşimşek); hypermedia-driven architecture
- **Mark Nottingham** — IETF HTTPbis working group chair; edits the HTTP/1.1, HTTP/2, and HTTP/3 specifications; HTTP semantics, caching, headers

**Carson Gross's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **Hypermedia as the engine of state** | The server controls application state through the HTML it returns — not through client-side logic or JSON payloads. An HTMX endpoint that returns data for the client to transform is doing it wrong. The response should be the transformed state, directly renderable. |
| **Partial responses must be self-consistent** | An HTMX swap target receives a fragment. That fragment must make sense on its own: correct IDs, correct ARIA relationships, correct HTMX attributes. A fragment that relies on surrounding DOM state it cannot see is fragile. |
| **HX-Redirect is a client-side redirect** | `HX-Redirect` triggers a full page navigation in the browser. It is appropriate after a state change that makes the current page stale (session start, step transition). Using it where `HX-Retarget` + a partial swap would suffice adds unnecessary page loads. |
| **HX-Retarget / HX-Reswap are escape valves** | Use them sparingly — when the HTMX attribute placement in the template can't express the swap target you need. Overuse is a sign the template structure is wrong. |
| **Out-of-band swaps (hx-swap-oob) for multi-target updates** | When a single action must update multiple disjoint areas of the DOM, include the secondary targets as `hx-swap-oob` elements in the response. Using JavaScript events or `HX-Trigger` to chain a second request is avoidable complexity. |
| **SSE for server-push** | Server-Sent Events are the right primitive for streaming AI responses — one-directional, simple, browser-native reconnect. The `htmx-ext-sse` extension wires them directly to HTMX swaps without JavaScript. When SSE is used, ensure events have named types so the extension can route them to the right target. |

**Mark Nottingham's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **Status codes are contracts** | `200 OK` means the request succeeded and the response body is the resource. `204 No Content` means success with no body — HTMX will not swap on a 204, which is sometimes exactly right. `422 Unprocessable Entity` means the server understood the request but rejected it for validation reasons — correct for form errors. `500` is for server faults, not for "command failed." |
| **Location and redirect semantics** | A `303 See Other` after a POST is the correct pattern for PRG (Post-Redirect-Get). HTMX's `HX-Redirect` bypasses this — the response to the POST is already a redirect header, so the browser doesn't re-POST on reload. This is intentional, but understand what it replaces. |
| **Cache-Control on partial responses** | HTMX partial responses that should not be cached must carry `Cache-Control: no-store`. Browser and CDN caching of HTMX fragments causes state staleness that is extremely hard to debug. |
| **Content-Type precision** | `text/html` for HTML fragments. `text/event-stream` for SSE. `application/json` for JSON. Wrong Content-Type causes silent parse failures in browsers and HTMX. |
| **Header hygiene** | Custom headers (`HX-*`) are application-level protocol. They must not leak into responses that cross origin boundaries without appropriate CORS configuration. |

*Synthesis:* Gross evaluates whether the hypermedia architecture is coherent — whether the server is truly driving state. Nottingham evaluates whether the HTTP layer is correct — status codes, headers, caching, Content-Type. A response can be correct HTTP but wrong hypermedia (returns JSON where HTML was needed) or correct hypermedia but wrong HTTP (returns 200 for a validation error). Both lenses are needed.

---

## UI Panel

*Active when `app/templates/**` or `app/static/**` files are in scope.*

- **Jeremy Keith** — *Resilient Web Design*, *HTML5 for Web Designers*; progressive enhancement, HTML-first architecture
- **Heydon Pickering** — *Inclusive Design Patterns*, *Inclusive Components*; accessibility, ARIA, inclusive UI
- **Adam Wathan** — creator of Tailwind CSS; utility-first CSS discipline, component extraction thresholds
- **Brad Frost** — *Atomic Design*; design systems, component composition, design token usage

**Jeremy Keith's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **HTML is the foundation** | The page must be meaningful before CSS loads and functional before JS runs. HTMX-enhanced elements should have sensible behavior without HTMX (a form still submits, a link still navigates). Progressive enhancement means each layer adds capability without being a prerequisite. |
| **Behavior belongs in HTML attributes, not JavaScript** | HTMX's `hx-get`, `hx-post`, `hx-target` are the right place for interaction declarations. JavaScript that imperatively sets up HTMX-equivalent behavior is the wrong layer. Alpine.js is the right escape hatch for client-side state that has no server equivalent — not for reimplementing server interaction. |
| **URLs are the identity of resources** | Every meaningful application state should have a URL. HTMX's `hx-push-url` is used exactly for this. A state that can only be reached by interaction (not by URL) is a resilience failure. |
| **Don't break the back button** | `hx-push-url` + `hx-history-elt` are the HTMX mechanism for preserving browser history. Page fragments that update without updating the URL silently break navigation expectations. |

**Heydon Pickering's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **ARIA is a repair tool, not a feature** | ARIA roles, properties, and states exist to repair semantic gaps in HTML — not to add meaning to `<div>` soup. The first question is always: is there a semantic HTML element that already does this? If yes, use it. |
| **Interactive elements must be keyboard reachable** | Every element a user can click must also be reachable and activatable via keyboard. HTMX-enhanced `<div>` or `<span>` elements are not focusable by default — use `<button>` or `<a>` instead. |
| **Live regions for dynamic content** | Content that updates without a page reload (HTMX swaps, SSE updates) must be announced to screen readers via `aria-live` or `role="status"`. The chat log uses `role="log"` + `aria-live="polite"` — this is correct; flag deviations. |
| **Focus management after dynamic updates** | When content is replaced by an HTMX swap, keyboard focus may land in an empty or irrelevant place. For significant content changes, focus should be moved explicitly to the new content's heading or the first interactive element. |
| **Color is not the only indicator** | Status, error states, and active states communicated only by color fail WCAG SC 1.4.1 (Use of Color). Always pair color with an additional indicator (icon, label, pattern, border). |

**Adam Wathan's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **Utilities express intent; components encode decisions** | A long class list on a `<div>` is not a problem — it is the design. A component abstraction is only warranted when the same combination of utilities appears in multiple places with identical meaning. Extract when you're duplicating a decision, not when you're duplicating markup. |
| **`@apply` is a last resort** | `@apply` compiles Tailwind utilities into CSS classes, losing the specificity and composition benefits of utilities. It exists for integrating with third-party CSS (like USWDS). Using it for in-project markup is usually a sign that a component-level abstraction (a Jinja macro or partial) is the right fix instead. |
| **Arbitrary values signal missing tokens** | `w-[337px]` is a sign that a design token should exist. Add it to `tailwind.config.js` and give it a meaningful name. Arbitrary values that appear once are usually fine; arbitrary values that appear in multiple places are a missing token. |
| **Responsive variants are explicit** | `md:flex-row`, `lg:hidden` — these are immediately readable. Implicit responsiveness hidden inside CSS classes is not. Tailwind's utility-first approach makes responsive behavior explicit at the markup level; preserve that property. |
| **Keep the config as the source of truth** | All custom colors, spacing, fonts, and breakpoints live in `tailwind.config.js`. Values that appear in CSS files or `style=` attributes are configuration leaking out of its container. |

**Brad Frost's key positions:**

| Position | What it means in practice |
|----------|--------------------------|
| **Atoms compose into molecules compose into organisms** | A USWDS `usa-button` is an atom. A form with a label, input, and button is a molecule. A step panel is an organism. When building custom components, identify which level they are and ensure they only reach down to atoms — never skip levels. |
| **Design tokens are the design system's API** | USWDS tokens (mapped into Tailwind via `tailwind.config.js`) are the contract between design and engineering. Using a raw hex value or pixel size that isn't a token breaks this contract — future design changes won't propagate. |
| **Components should be agnostic about context** | A well-designed component doesn't know where it lives in the page. Flag components that adjust their appearance based on their parent (margin adjustments, color overrides) — these tight couplings prevent reuse. |
| **The pattern library exists; use it** | USWDS ships canonical components (`usa-alert`, `usa-summary-box`, `usa-card`, `usa-tag`, `usa-accordion`, `usa-modal`) that carry accessibility, styling, and behavior. Building a Tailwind-styled clone of any of these is a design system violation, not a shortcut. |

*Synthesis across UI panelists:* Keith establishes the HTML/behavioral foundation; Pickering evaluates whether it's accessible; Wathan evaluates whether the CSS is disciplined; Frost evaluates whether the component boundaries respect the design system. A finding that fails all four — a `<div>` with an `onclick` that renders a Tailwind-cloned alert — is a BLOCKER.

---

## AI/LLM Panel

*Active when `app/clients/**` files are in scope or when the code under review constructs prompts, invokes LLMs, or processes LLM output.*

- **Simon Willison** — creator of Datasette, simonwillison.net; coined "prompt injection" in the LLM context; AI application design and observability

*(Willison's full position reference is unchanged from the existing critique — see Dimension 15 below.)*

---

## Expert Positions Reference (Core Panel)

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
|-------------------|--------------------------|
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
|---------|-----------------|
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
*Core panel — Ousterhout, Fowler*

- Are modules deep (simple interfaces hiding significant complexity) or shallow (thin wrappers)?
- Do abstractions leak implementation details through their interfaces?
- Are there pass-through methods that add no value? (Fowler: Middle Man)
- Do abstractions at the same layer represent the same level of generality?

---

### Dimension 2: Decomposition & Entanglement
*Core panel — Martin, Ousterhout synthesis*

- Entanglement test: does understanding any method require reading others to reconstruct context?
- Are there shallow extracted methods — single-line wrappers — that add indirection without adding meaning?
- Are related pieces of logic split when they share state and should be read together?
- "And" test (Fowler/Martin): if you can't describe a function without saying "and," it has multiple responsibilities.

---

### Dimension 3: Naming Precision
*Core panel — all three*

- Are names precise? Do they convey exactly what the entity is without requiring the reader to check the implementation?
- Vague nouns: Manager, Handler, Helper, Util, Data, Info, Processor?
- Misleading names? Boolean names unambiguous? Collection names reflect element type?

---

### Dimension 4: Documentation & Comments
*Core panel — Ousterhout, Fowler, Martin*

Apply the three-way test: interfaces → document; why-comments → write; what-comments → remove.

- Is the contract documented for every public function? Preconditions, return value, errors?
- Is the documentation accurate? (Stale comments are worse than none.)
- Are there non-obvious decisions explained? Rejected alternatives?
- Are there TODO comments without tracking references?

---

### Dimension 5: Code Smells
*Core panel — Fowler, Martin, Beck*

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
*Core panel — Martin (SOLID), Ousterhout*

Apply only where clearly evidenced:

- **SRP**: one reason to change?
- **OCP**: new behaviors without modifying existing code?
- **DIP**: higher-level modules depend on abstractions, not concretions?
- **Information Hiding**: would a change to the implementation require changes to callers?

---

### Dimension 7: Test Quality
*Core panel — Fowler, Martin, Beck*

- Do tests verify **behavior** or **implementation**?
- Are mocks limited to the external boundary (I/O, network, time)?
- Are tests independent, deterministic?
- Edge cases: empty inputs, nulls, error paths, concurrent access?
- Beck: does the test read like a specification? Can you understand what the system does from the test alone?

---

### Dimension 8: Security
*Core panel — McGraw*

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
*Core panel — Evans*

- Does code vocabulary match the domain's spoken language?
- Are entities compared by identity, value objects by value?
- Are aggregate invariants enforced through the aggregate root?
- Is domain logic in the domain layer, not scattered across routes?
- Are significant state changes named events rather than silent side effects?

---

### Dimension 10: Pythonic Design
*Python panel — Hettinger*

- **Stdlib first**: reimplementing `Counter`, `defaultdict`, `chain`, `islice`, `lru_cache`?
- **Iteration idioms**: `enumerate` over `range(len(...))`? `zip` over index-synchronized loops?
- **Comprehension appropriateness**: used where they improve clarity, extracted where they don't?
- **EAFP vs LBYL**: `try/except` where checking-then-acting would introduce a race?
- **Type annotation completeness**: all public functions fully annotated?
- **`dataclass`/`NamedTuple` over raw dicts** for structured data?
- **Context managers** for all resource management?

---

### Dimension 11: Async & Python Internals
*Python panel — Beazley, Goetz*

| Hazard | What to look for |
|--------|-----------------|
| **Compound actions across `await`** | Check-then-act or read-modify-write with an `await` between the check and the act — another coroutine can run during the await and invalidate the check. |
| **Unguarded shared mutable state** | A mutable object accessed from more than one coroutine or thread without a lock or queue. |
| **`asyncio.to_thread` boundary crossings** | Mutable objects passed as arguments to `asyncio.to_thread` cross into a real thread and need locking or must be immutable. |
| **Silent `CancelledError` swallowing** | `except Exception` that catches `CancelledError` without re-raising stops cancellation propagation — the task appears to hang. |
| **`asyncio.gather` failure semantics** | When one coroutine in `gather` raises, others continue by default. Partial completion leaves state inconsistent unless `return_exceptions=True` is used deliberately. |
| **Safe publication** | An object initialized in one coroutine/thread published to shared state before fully initialized. |

Goetz's design-level questions: can you name, for every shared mutable field, which lock or discipline protects it? Is thread confinement used where possible?

---

### Dimension 12: HTTP/Hypermedia Design
*HTTP/API panel — Gross, Nottingham. Active when `app/routes/**` in scope.*

| Hazard | What to look for |
|--------|-----------------|
| **Wrong status code** | `500` for a user-facing failure that should be `422`; `200` returned when `204 No Content` would suppress an unwanted swap; `302` where `303 See Other` is the correct PRG pattern. |
| **Partial response not self-consistent** | An HTMX swap target fragment that relies on surrounding DOM state (IDs, ARIA relationships, HTMX attributes on ancestors) it cannot see. |
| **HX-Redirect overuse** | `HX-Redirect` triggers a full page navigation — used where a partial swap + `HX-Retarget` would suffice, adding unnecessary page loads. |
| **Missing cache control** | HTMX partial responses or SSE endpoints without `Cache-Control: no-store` where caching would cause state staleness. |
| **Wrong Content-Type** | HTML fragments must be `text/html`; SSE streams must be `text/event-stream`; JSON must be `application/json`. Wrong type causes silent parse failures. |
| **Response drives data, not state** | An HTMX endpoint returning JSON for the client to transform is incorrect hypermedia design. The response should be the rendered state fragment, directly swappable. |
| **Missing out-of-band swaps** | A single action updating multiple disjoint DOM regions, handled by chaining a second HTMX request via `HX-Trigger`, when `hx-swap-oob` in the response would be cleaner. |
| **SSE event naming** | SSE events without explicit `event:` type fields cannot be routed by `htmx-ext-sse` to specific targets. |
| **HX-* header CORS leakage** | Custom HX-* response headers on endpoints that might be accessed cross-origin without appropriate CORS configuration. |

Gross's design-level question: is the server truly driving application state through the HTML it returns, or is the client assembling state from data the server provides?

---

### Dimension 13: UI Consistency (USWDS + Tailwind)
*UI panel. Active when `app/templates/**` or `app/static/**` in scope. Read `.claude/docs/ui-style-guide.md` before producing findings.*

| Hazard | What to look for |
|--------|-----------------|
| **Tailwind on USWDS components** | A `usa-*` element carrying Tailwind utility classes directly. Layout belongs on a wrapper `<div>`. |
| **USWDS utility classes** | `margin-y-*`, `padding-*`, `display-flex`, `flex-align-*`, `font-sans-*`, `text-bold`, `radius-*` on our markup. Replace with Tailwind equivalents. |
| **Inline styles** | `style="..."` attributes. Extend `tailwind.config.js` instead. |
| **Tailwind clones of USWDS components** | Custom markup that reproduces `usa-alert`, `usa-tag`, `usa-card`, `usa-summary-box`, `usa-modal`, etc. Use the canonical component. |
| **Missing HTMX bridge re-init** | A USWDS component delivered via HTMX swap that DOM-transforms (combo-box, file-input, date-picker) without a branch in `app/static/js/htmx-uswds-bridge.js`. |

Run `.claude/hooks/analyze/ui-consistency.sh` and cite its output line-by-line as findings. Severity: mixing-system patterns are MAJOR by default; a Tailwind clone of a USWDS interactive component is BLOCKER.

---

### Dimension 14: Frontend Architecture
*UI panel — Keith, Pickering, Wathan, Frost. Active when `app/templates/**` or `app/static/**` in scope.*

| Lens | What to look for |
|------|-----------------|
| **Keith — progressive enhancement** | Does the page remain meaningful and functional without JS? Are HTMX-enhanced elements using semantic HTML (`<button>`, `<a>`, `<form>`) rather than `<div>` + `onclick`? Do meaningful states have URLs (`hx-push-url`)? |
| **Keith — behavioral layering** | Is Alpine.js used only for client-side state with no server equivalent? Is HTMX used for all server interactions? JavaScript that reimplements HTMX behavior in the wrong layer. |
| **Pickering — ARIA correctness** | Are `role`, `aria-*` attributes used to repair semantic gaps, not to add meaning to `<div>` soup? Is the first question always "is there a semantic HTML element that does this"? |
| **Pickering — keyboard accessibility** | Every interactive element reachable and activatable via keyboard. HTMX-enhanced non-button elements that lack `tabindex` and `onkeypress`. |
| **Pickering — live regions** | HTMX swap targets that update dynamically without `aria-live` or `role="log"/"status"`. Screen readers won't announce the update. |
| **Pickering — focus management** | After a significant HTMX swap (e.g., step transition, chat message), is focus managed explicitly to the new content? |
| **Pickering — color alone** | Status or error states communicated only by color without a secondary indicator (icon, label, border). |
| **Wathan — extract threshold** | Repeated identical utility combinations appearing in 3+ places with the same meaning → extract to a Jinja macro or partial. One-off utility combinations are correct Tailwind usage. |
| **Wathan — arbitrary values** | `w-[337px]`, `text-[13px]` appearing multiple times → missing design token in `tailwind.config.js`. |
| **Wathan — `@apply` overuse** | `@apply` in project CSS for non-third-party integration → the fix is a Jinja macro, not a CSS class. |
| **Frost — design system integrity** | Custom components that duplicate existing USWDS atoms, molecules, or organisms. Components that adjust themselves based on parent context (tight coupling). |
| **Frost — token discipline** | Raw hex values or pixel sizes not from `tailwind.config.js` design tokens. |

---

### Dimension 15: AI Application Design
*AI/LLM panel — Willison. Active when `app/clients/**` or LLM integration is in scope.*

| Hazard | What to look for |
|--------|-----------------|
| **Undocumented trust escalation** | `--dangerously-skip-permissions` or equivalent without a comment explaining the trust decision, alternatives considered, and scope of capability granted. |
| **Prompt injection surface** | External content (uploaded files, user messages, web data) reaching the LLM's context window while the model has write-capable or side-effecting tools available. |
| **Text-parsed success detection** | Code reading the LLM's natural-language output to determine success. Prefer structured signals: exit code, file written, record created. |
| **Missing observability** | LLM invocations without logging: (a) what was sent, (b) what was received, (c) what tool calls were made. |
| **Unbounded tool capabilities** | LLM given write access when read-only would suffice. |
| **Abstracted context content** | Prompt construction hidden in helpers that make the full content sent to the model invisible at the call site. |

Willison's design questions: what external content can reach the context window? What would an attacker do if they could inject a sentence into any document the model reads? Can a developer reconstruct exactly what was sent and received for any production LLM call?

---

## Secondary Panel

Consult only when the primary panel produces a genuine impasse — competing positions that are both defensible and the synthesis cannot resolve.

The secondary panel does not re-read the full codebase. It receives the contested finding, competing positions, specific code, and one focused question. It renders a specialist verdict on that question only.

**When to invoke:**
- Two or more primary experts take incompatible positions and synthesis produces "it depends" with no clear decision criteria
- A finding requires specialist knowledge the primary panel cannot resolve

### Secondary Panelist: Luciano Ramalho (*Fluent Python*)

**Domain:** Python's data model, structural subtyping, protocol design.

**Invoke when** a finding involves: dunder method implementation, the choice between `typing.Protocol` / `ABC` / duck typing, whether a class warrants `__slots__`, disagreement between Hettinger and another panelist about stdlib types or protocols.

**Ramalho's positions:** Classes that don't implement the Python data model correctly are second-class objects. Prefer `typing.Protocol` over `ABC` when callers don't need to inherit. Implement `__repr__` for every class representing a meaningful domain object. `__slots__` is an optimization, not a design pattern. Mutable default arguments are bugs.

---

### Secondary Panelist: Sara Soueidan (*Practical SVG*, CSS animations, accessibility engineering)

**Domain:** CSS architecture, SVG, ARIA implementation correctness, the intersection of CSS and accessibility.

**Invoke when** a finding involves: conflicting positions between Pickering (accessibility requirement) and Wathan (CSS discipline) or Frost (design system rule); SVG icon usage and accessibility (`aria-hidden`, `focusable="false"`, title elements); complex animation or transition code where accessibility (prefers-reduced-motion) and visual design conflict; ARIA live region implementation where the correct markup is genuinely ambiguous.

**Soueidan's positions:**
- SVG icons used decoratively must have `aria-hidden="true"` and `focusable="false"`. SVG icons that convey meaning must have an accessible label — either a `<title>` element (with `aria-labelledby`) or an `aria-label` on the parent element.
- `prefers-reduced-motion` is not optional. Any animation or transition that is not purely opacity-based must be disabled or substantially reduced for users who have requested it.
- CSS custom properties (variables) are the correct implementation layer for design tokens — they are runtime-configurable and inspectable in DevTools in a way that Tailwind's compiled classes are not. For values that must be dynamic (theming, user preferences), prefer CSS variables over Tailwind arbitrary values.
- Focus indicators must be visible in both light and dark modes, and must meet WCAG 1.4.11 (Non-Text Contrast) minimum 3:1 ratio against adjacent colors. The default browser outline is often insufficient.

**Format for referral:** State the contested finding ID, quote the competing primary-panel positions, quote the specific code, and ask: *"Soueidan: given [position A] vs [position B], which is the correct approach for this case, and why?"*

---

## Output Format

Write the critique as a structured report. Do not write anything until you have read all target files. After producing the report, write it to `CRITIQUE.md` in the current working directory.

```
═══════════════════════════════════════════════════════
  EXPERT CODE CRITIQUE
  Target: [file(s) reviewed]
  Active panels: [Core | + Python | + UI | + HTTP/API | + AI/LLM]
  Date: [today's date]
═══════════════════════════════════════════════════════

## Summary

[3–5 sentences. Overall assessment. Primary strengths. Primary concerns. Gestalt only — no findings listed here.]

## Finding Table

| ID | Severity | Dimension | Panel | Location | Finding |
|----|----------|-----------|-------|----------|---------|
| C-01 | BLOCKER/MAJOR/MINOR/OBS | [dimension] | [panel] | file:line | [one-line description] |

Severity guide:
- BLOCKER: Serious design problem likely to cause bugs, maintenance failure, or security issues. Must be resolved before shipping.
- MAJOR: Clear violation of a principle with meaningful consequences. Fix before merge.
- MINOR: Improvement opportunity. Fix if the code is being touched anyway.
- OBS: Observation worth noting. May reflect a legitimate tradeoff.

## Detailed Findings

For each finding:

### C-XX: [Short Title]
**Severity:** [BLOCKER/MAJOR/MINOR/OBS]
**Dimension:** [dimension name]
**Panel:** [which panel raised this]
**Location:** `file:line`

**What I see:**
[Describe the specific code — quote or describe what is actually there.]

**Expert Perspective:**
[Which expert(s) flag this? If experts disagree, name the disagreement explicitly.]

**Synthesis:**
[What should be done, and why? If a genuine tradeoff, say so.]

**Suggested direction:**
[Concrete, specific recommendation. Not "consider refactoring" — say what to extract, rename, remove, or add.]

---

## Codebase Patterns

*This section looks beyond the changed files. What does this change reveal about habits, patterns, or systemic tendencies in the broader codebase?*

For each observation:

### P-XX: [Short Title]
**Type:** [Recurring pattern / Systemic gap / Positive pattern worth continuing]
**Where it appears:** [list of files/modules — not just the ones in scope]

[2–4 sentences describing the pattern, whether it's a problem, and what the systemic fix would be. Reference the "when to fix" note convention if the pattern reflects a deliberate simplification that needs a revisit trigger.]

---

## Highlights

[2–4 things the code does well. Be specific — name the exact pattern or decision and why it reflects good practice.]

## Verdict

**Recommended action:** [APPROVE / REVISE / MAJOR REWORK]
**Blocker count:** [N]
**Major count:** [N]
**Summary:** [One sentence on what must happen before this code is production-ready.]
```

---

## Conduct Rules

1. **Be specific.** Every finding must reference a file and line (or method/class name). No finding based on general impression.
2. **Cite the code.** Quote or precisely describe what you observed — do not paraphrase vaguely.
3. **Acknowledge tradeoffs.** If two experts disagree, name the disagreement. The user deserves to understand the actual debate, not a false consensus.
4. **Do not over-decompose.** Resist the urge to flag every function as too long. Apply Ousterhout's depth test before flagging.
5. **Do not generate code.** Surface findings and directions. Describe the refactoring precisely. Do not write replacement code unless asked.
6. **No padding.** Every finding must justify its severity. Do not flag MAJOR issues that are OBS-level.
7. **Prioritize by impact.** BLOCKERs first. If there are more than 10 findings, group MINOR/OBS findings into a summary table.
8. **Security flaws are BLOCKERs unconditionally.** A design-level security flaw (wrong trust boundary, missing authorization layer, user input reaching a subprocess) blocks shipment. Do not downgrade.
9. **Architectural prompt injection is a BLOCKER.** External, attacker-influenced content reaching an LLM context window while the model has write-capable tools available, with no documented mitigation, is a design-level flaw.
10. **Codebase Patterns are not findings.** They are observations about the broader codebase surfaced by this change. They do not count toward the blocker/major totals and do not affect the Verdict — they inform the next design or refactoring session.

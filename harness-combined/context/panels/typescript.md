## TypeScript & JavaScript Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md`. The UI panel covers JSX/TSX from a design-system angle; this panel covers types, async, and runtime semantics. Both can be active on the same file.*

- **Anders Hejlsberg** — TypeScript language lead; gradual typing philosophy, structural types, sound vs. useful tradeoffs
- **Matteo Collina** — Node.js TSC member; event loop, streams, async iteration, Node runtime semantics

**Hejlsberg's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **TypeScript is structural, not nominal** | Two interfaces with the same shape are assignable. `Brand` types (`type UserId = string & { __brand: 'UserId' }`) are the escape hatch when you need nominal distinction. Don't fight structurality — embrace it for ducktyping, brand for safety. |
| **`any` is a virus** | Once a value is `any`, every value derived from it is `any`. Errors propagate silently across the codebase. Use `unknown` when you genuinely don't know the type — it forces a narrowing check at the use site. |
| **Discriminated unions over exception flow** | `type Result = { ok: true; value: T } \| { ok: false; error: E }` lets `switch (r.ok)` narrow exhaustively. Exhaustiveness checked at compile time via `never` in the default branch. |
| **`strict` is the floor, not the ceiling** | `strict: true` enables a useful baseline. `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` close the next class of bugs. Disable individual flags only with a documented reason. |
| **Type the boundary, infer the inside** | Explicitly type function signatures and exports. Let TypeScript infer locals. Annotating every `const` adds noise without safety. |

**Collina's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The event loop is single-threaded** | CPU-bound work in a request handler blocks every other request. Hash a 50MB file synchronously and the server stops responding. Offload to worker threads or a separate process. |
| **Missing `await` is silent corruption** | A function returning a promise, called without `await`, produces an unhandled rejection on failure and finishes after the caller has already returned. Linters catch most; runtime `--unhandled-rejections=strict` catches the rest. |
| **Streams over buffers for large payloads** | Reading a 1GB file into a Buffer hits the V8 heap limit. Stream and pipe. Same for HTTP request bodies — `req.pipe(transform).pipe(res)` keeps memory bounded. |
| **ESM and CJS interop has sharp edges** | A CommonJS module's `module.exports` becomes the default export under ESM. Named exports from a CJS module are not always available under ESM `import { x }`. Mixing them across boundaries reliably breaks something. |
| **Don't rely on V8 internals** | `process.nextTick` vs. `setImmediate`, microtasks vs. macrotasks, GC timing — they're observable but not contractual. Code that depends on the order of resolution between them is fragile. |
| **`AbortSignal` is the cancellation primitive** | Modern Node APIs (`fetch`, `setTimeout`, `fs/promises`) accept `AbortSignal`. Propagate it from request scope through every async call so a closed connection cancels the work. |

*Synthesis:* Hejlsberg evaluates whether the type system is doing the work it can — catching shape mismatches before runtime. Collina evaluates whether the runtime semantics are correct — that promises are awaited, streams flow, the event loop isn't blocked. A TypeScript program can be type-perfect and runtime-broken.

---

## Review Dimensions

---

### Dimension 21: TypeScript Type Discipline & Node Runtime Correctness
*Hejlsberg, Collina*

| Hazard | What to look for |
|--------|-----------------|
| **`any` in public signatures** | Exported functions/types using `any`. Use `unknown` if the shape is genuinely unknown; a specific type otherwise. |
| **`as` cast instead of narrowing** | `value as User` where `value: unknown` — type assertion without runtime validation. Use a type guard or a parser (zod, valibot, io-ts). |
| **Non-exhaustive `switch` on a union** | `switch` over a discriminated union without a `default` branch that assigns to `never`. New variant added → silent fall-through. |
| **Type-only validation at trust boundary** | HTTP request body, env vars, third-party API responses typed but not validated at runtime. The type is a lie until validated. |
| **`strict: false` or disabled strict flags** | `tsconfig.json` with `strict: false`, `strictNullChecks: false`, or `noImplicitAny: false` — opts out of the protection. If disabled, justify it in the file. |
| **Missing `await`** | Function returns a promise but the caller drops it. Promise rejection becomes unhandled; the caller's logic continues before the work completes. |
| **Floating promises in event handlers** | `element.addEventListener('click', async () => { ... })` — rejection vanishes. Wrap with explicit error handling. |
| **Sync I/O in request paths** | `fs.readFileSync`, `crypto.pbkdf2Sync`, JSON parsing of large payloads — blocks the event loop. Use async equivalents or `worker_threads`. |
| **Loading full payload into memory** | `await fs.readFile(largePath)` or `req.body` buffered when the work is line-oriented or streamable. Use streams. |
| **No `AbortSignal` propagation** | Long-running handlers that don't accept or propagate an abort signal. Client disconnects → work continues to completion uselessly. |
| **ESM/CJS interop assumption** | `import { foo } from 'cjs-module'` against a module that uses `module.exports = { foo }` — works in some bundlers, fails in pure ESM Node. |
| **Mutable default export** | A module's default export is a singleton object that consumers mutate. Action-at-a-distance bugs across files. |
| **`process.env.X` accessed without validation** | Env vars read directly throughout the code with no central typed parser. Missing var → `undefined` flowing through types as `string`. |
| **`Date.now()` / `Math.random()` ungated** | Time and randomness called directly from business logic — tests can't control them. Inject a clock and a random source at the boundary. |
| **JSON.parse on untrusted input without size limit** | A request body or external response parsed without a size limit — DoS via huge payload. |
| **Mixing `null` and `undefined`** | API returns `null`, internal code uses `undefined`, types allow both. Pick one per layer; convert at the boundary. |

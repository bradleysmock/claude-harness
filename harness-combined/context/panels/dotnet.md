## .NET Panel

*Activation is governed by the trigger table in `context/panels/triggers.md` — that table is the single source for the file patterns and dependency signals that load this panel. Generic HTTP correctness defers to `http-api.md` and raw SQL/ORM concerns to `database.md`; this panel covers .NET-specific machinery — async/await discipline, DI lifetimes, EF Core query behavior, and nullable reference types.*

- **Stephen Cleary** — *Concurrency in C#*; the async/await authority — synchronization context, deadlocks, and cancellation
- **David Fowler** — ASP.NET Core architect at Microsoft; author of the async and DI guidance the framework is built on

**Cleary's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Async all the way, or deadlock** | Blocking on async code (`.Result`, `.Wait()`, `.GetAwaiter().GetResult()`) on a thread with a synchronization context deadlocks. The fix is not `ConfigureAwait(false)` at the block site — it is to await all the way up. Sync-over-async is the single most common .NET hang. |
| **`ConfigureAwait(false)` in library code** | Library and framework code that does not need the captured context should use `ConfigureAwait(false)` to avoid forcing continuations back onto it — reducing deadlock risk and context-switch cost. Application/UI code that touches context-bound state keeps the default. |
| **`async void` is fire-and-forget with no error path** | An `async void` method's exceptions cannot be caught by the caller and crash the process. Only event handlers should be `async void`; everything else returns `Task`. |
| **Cancellation is cooperative and must flow** | A `CancellationToken` accepted but not passed to the inner awaited calls is decoration. Propagate it to every async call and honor `OperationCanceledException` — do not swallow it. |

**Fowler's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **DI lifetimes are a correctness contract** | Injecting a scoped service into a singleton captures the first scope forever — a classic source of stale data and cross-request leakage (a "captive dependency"). `DbContext` is scoped; never hold it in a singleton or a static. |
| **`DbContext` is not thread-safe** | One `DbContext` used concurrently across parallel awaits corrupts its change tracker. One unit of work per context per request; do not share it across `Task.WhenAll` branches. |
| **Dispose what you own** | `IDisposable`/`IAsyncDisposable` resources (streams, `HttpClient` handlers, DB connections) must be disposed — `using`/`await using` or DI-managed lifetime. But do *not* create a new `HttpClient` per call; use `IHttpClientFactory` to avoid socket exhaustion. |
| **Nullable reference types are a design signal** | With NRTs enabled, `?` on a reference type is a contract. Suppressing warnings with `!` (null-forgiving) to silence the compiler re-introduces the null bug the feature exists to catch. |

*Synthesis:* Cleary evaluates whether the async and cancellation machinery is correct — no sync-over-async deadlocks, no `async void`, tokens that actually flow. Fowler evaluates whether the object lifecycle is correct — DI lifetimes, `DbContext` scoping, disposal, and honest nullability. Code can be flawlessly async and still leak a scoped `DbContext` into a singleton; it can have pristine DI and deadlock on a `.Result`. Both lenses matter.

---

## Review Dimensions

---

### Dimension 53: Async Discipline, Lifetimes & EF Core Hygiene
*Cleary, Fowler*

| Hazard | What to look for |
|--------|-----------------|
| **Sync-over-async** | `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()` on a `Task` in request or library code — deadlocks under a synchronization context and starves the thread pool. |
| **`async void`** | Any `async void` method that is not an event handler — its exceptions escape all `try/catch` and crash the process. |
| **Missing `ConfigureAwait(false)` in library code** | Library/framework code awaiting without `ConfigureAwait(false)` where the captured context is not needed. No effect in a contextless host (modern ASP.NET Core has no `SynchronizationContext`); it matters in libraries that may run under a UI or legacy ASP.NET context. |
| **Unpropagated `CancellationToken`** | A token accepted at the entry point but not threaded into inner async/EF calls, or an `OperationCanceledException` swallowed by a broad `catch`. |
| **Captive dependency** | A scoped (or transient) service injected into a singleton — captures one scope for the process lifetime, leaking state across requests. |
| **`DbContext` misuse** | A `DbContext` held in a singleton/static, or shared across concurrent `Task.WhenAll` branches — the change tracker is not thread-safe. |
| **EF Core N+1 / client-side eval** | Lazy-loaded navigations in a loop, missing `Include`, or a `.Where`/`.Select` that silently evaluates in memory after materializing the whole table (overlap with Database panel). |
| **Tracking queries for read-only paths** | Read-only queries without `AsNoTracking()` — needless change-tracker overhead and accidental updates. |
| **Undisposed resource / `HttpClient` per call** | An `IDisposable` not wrapped in `using`/DI, or a `new HttpClient()` per request causing socket exhaustion — use `IHttpClientFactory`. |
| **Null-forgiving suppression** | `!` (null-forgiving operator) or `#nullable disable` used to silence NRT warnings instead of handling the null case. |

Cleary's design question: follow one request from the controller to the database — is it `await`ed the whole way, with the `CancellationToken` passed to every call, and no `.Result` anywhere on the path? Fowler's: for every service registered, does its lifetime outlive nothing it captures, and is the `DbContext` confined to exactly one unit of work per request?

## Go Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Rob Pike** — Go language co-author; simplicity over cleverness, orthogonal primitives, "clear is better than clever"
- **William Kennedy** — *Ultimate Go*; idiomatic Go semantics, concurrency patterns, the runtime model

**Pike's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **A little copying is better than a little dependency** | Don't pull a package for two lines of code. Don't write a generic helper for code used once. The standard library plus a small amount of duplication beats premature abstraction. |
| **Errors are values** | `if err != nil { return err }` is the idiom. Resist the urge to wrap it in a "framework." Use `errors.Is` / `errors.As` / `%w` for context; don't invent new error-handling DSLs. |
| **Don't communicate by sharing memory; share memory by communicating** | Channels are the synchronization primitive. A struct with a mutex and a flag is often a channel waiting to be refactored. |
| **Interfaces define what you need, not what you provide** | Define interfaces at the *consumer*, with the smallest set of methods that consumer actually uses. Big "provider interface" definitions in a package that everyone implements is the wrong direction. |
| **Naming: short for narrow scope, longer for wider** | Loop variable: `i`. Package-level export: `RequestProcessor`. The shorter the lifetime, the shorter the name. |

**Kennedy's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Goroutines leak silently** | A goroutine blocked on a channel receive that never sends — invisible until you OOM. Every goroutine you start must have a documented termination path: completion, context cancellation, or channel close. |
| **`context.Context` is the cancellation propagator** | Every function that does I/O takes a `ctx context.Context` as the *first* parameter. Long-running work must select on `ctx.Done()`. Code that creates a `context.Background()` deep in the call stack discards the caller's cancellation. |
| **Defer is for cleanup, not for ordering critical logic** | `defer file.Close()` — correct. `defer publishEvent()` for business logic that must run — wrong; it runs in undefined contexts and its error is ignored. |
| **Return concrete, accept interfaces** | Functions take interface parameters (to be testable and flexible) and return concrete types (so callers can use methods not in any interface). The opposite locks callers into your abstraction. |
| **Pointer vs value receivers** | Mixing pointer and value receivers on the same type confuses the method set and breaks interface satisfaction in subtle ways. Pick one, document why. |
| **The `nil` interface trap** | A typed-nil pointer assigned to an interface variable is not equal to `nil` — the interface holds the type and a nil pointer. `if err != nil` against such a value succeeds when callers expect it to fail. Return untyped `nil` for "no error." |

*Synthesis:* Pike evaluates whether the code embodies Go's design philosophy — small, orthogonal, boringly explicit. Kennedy evaluates whether it correctly handles Go's runtime model — goroutines, contexts, channels, the method set. A Go program can be idiomatic-looking and concurrency-broken; or correct and full of imported abstractions Go's stdlib already provides.

---

## Review Dimensions

---

### Dimension 24: Go Idioms & Concurrency Correctness
*Pike, Kennedy*

| Hazard | What to look for |
|--------|-----------------|
| **Goroutine without termination path** | `go func() { ... }()` with no `context`, no `defer wg.Done()`, no channel close — fire-and-forget. Document the termination condition or don't start the goroutine. |
| **Discarded `context.Context`** | Function takes `ctx` but calls into another I/O function with `context.Background()` or `context.TODO()`. Caller's cancellation is lost. |
| **Missing `ctx.Done()` in select** | Long-running goroutine with `select { case msg := <-ch: ... }` and no `case <-ctx.Done(): return`. Unkillable. |
| **Mutex protecting one field across many methods** | A struct with a `sync.Mutex` that protects only one piece of state — extract a type, embed `sync.Mutex`, scope the locking. Or replace with `atomic.Value` / channels. |
| **Channel direction not constrained at boundaries** | Function accepting `chan T` when it only sends or only receives. Use `chan<- T` / `<-chan T` to encode intent. |
| **`err` ignored at top of function** | `result, _ := doThing()` — explicit discard. Sometimes correct, but every one needs justification. |
| **Wrapped error losing type** | `return fmt.Errorf("doing thing: %v", err)` — `%v` flattens to string, breaking `errors.Is/As`. Use `%w`. |
| **Pointer/value receiver mix on one type** | Some methods on `*T`, others on `T`. Pick one; mixing breaks the method set for `T` vs `*T` and confuses interface satisfaction. |
| **Returning typed-nil for error** | `var p *MyError; return p` — caller's `if err != nil` succeeds even though the intent was nil. Return untyped `nil`. |
| **Defer for non-cleanup logic** | `defer publishMetric()` for business-critical work. Cleanup only; never silent error swallowing. |
| **Interface defined on provider side, not consumer** | A package exports a big interface and expects consumers to satisfy it. Invert — let consumers define the minimal interface they need. |
| **Stdlib reimplemented** | Custom `Set` over a `map[K]struct{}` wrapper, custom retry loop where `context.WithTimeout` + a small loop would do, custom `sync.Once` equivalent. |
| **`init()` doing work** | `func init()` that opens connections, reads files, mutates package globals. Init runs at import time with no error path; surprises pile up. |
| **Goroutine capturing loop variable** | Pre-Go 1.22: `for _, x := range xs { go func() { use(x) }() }` — every goroutine sees the final `x`. Capture explicitly or shadow. |
| **`panic` for ordinary error conditions** | `panic(err)` used as control flow. Panics are for unrecoverable invariant violations; return errors otherwise. |
| **HTTP client without timeout** | `http.Get(...)` or `http.DefaultClient` used directly — no timeout. Construct an explicit `http.Client` with `Timeout`. |
| **Unbounded `sync.WaitGroup` / goroutine fanout** | `for _, x := range xs { go work(x) }` without a worker pool — one goroutine per item, no concurrency limit. |

Kennedy's design question: for every goroutine started in this code, can you point to what terminates it, and what happens to its error if it has one?

## Rust Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Niko Matsakis** — Rust language team lead; ownership and borrowing model, lifetimes, async runtime semantics, "fearless concurrency"
- **Jon Gjengset** — *Rust for Rustaceans*; idiomatic API design, trait and lifetime patterns, when `unsafe` is justified

**Matsakis's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Ownership is the API** | A function signature taking `String` vs `&str` vs `&mut String` vs `Cow<'_, str>` is a contract about who allocates, who can mutate, and how long the value lives. Callers shape their code around this signature — change it carelessly and every caller pays. |
| **Lifetimes describe relationships, not durations** | A `'a` parameter says "the returned reference borrows from this input." It is not a duration in seconds. Code that fights the borrow checker with `'static` or excessive `Arc` is usually expressing a relationship wrong. |
| **`Send` and `Sync` are the concurrency contract** | A type is `Send` if it can move to another thread, `Sync` if it can be shared by reference. The compiler enforces this — but `unsafe impl Send` lets you lie. Code that does this without a safety argument is a data race waiting to be noticed. |
| **Async is cooperative; futures must be polled** | A future does nothing until `.await`ed or spawned. Code that creates futures and discards them runs nothing. Code that holds a `MutexGuard` across `.await` blocks the runtime — use `tokio::sync::Mutex`, not `std::sync::Mutex`, in async code. |
| **Cancellation is implicit at every `.await`** | A `.await` point is where the future may be dropped. Any state mutation that must be paired with a cleanup must be wrapped in a guard (RAII) — not in code after the `.await`. |

**Gjengset's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Errors are values; design the error type** | A library that returns `Box<dyn Error>` or `anyhow::Error` everywhere makes callers unable to match on specific failures. Define an error enum with `thiserror` for libraries; reserve `anyhow` for applications/bins. |
| **`unwrap()` and `expect()` are unrecoverable claims** | Each one is a claim: "this cannot fail." In production code, the claim is a panic in disguise. `expect("must be valid")` with no comment explaining *why* it cannot fail is the smell. |
| **Prefer iterators over indexed loops** | `for i in 0..v.len() { ... v[i] ... }` defeats bounds-check elision and obscures intent. Iterator chains compose, optimize well, and express intent. |
| **`clone()` is sometimes correct, often a workaround** | Cloning to escape a borrow-checker error is fine when the data is small. Cloning a large `Vec` or `String` every iteration is a performance bug. Each `clone()` deserves a moment of thought. |
| **`unsafe` is a contract, not an escape hatch** | Every `unsafe` block must have a `// SAFETY:` comment explaining the invariants the caller is upholding. `unsafe` without justification reverses the language's primary value proposition. |
| **Trait objects (`dyn Trait`) have a cost** | Dynamic dispatch and indirection. Use generics for hot paths; reserve `dyn` for heterogeneous collections and plugin-like extension points. |
| **API design: accept generic, return concrete** | Functions take `impl AsRef<Path>`, `impl IntoIterator<...>`, etc. (flexible for callers) and return concrete types (so callers know what they're getting). |

*Synthesis:* Matsakis evaluates whether the code respects Rust's core abstractions — ownership, lifetimes, the async model. Gjengset evaluates whether the API design is one a downstream user would thank you for — error types, allocation patterns, when to reach for `unsafe`. A Rust program can compile cleanly and still be a maintenance trap (everything `Arc<Mutex<T>>`, `unwrap()` scattered through happy paths) or fight the borrow checker into a knot the compiler accepts but no human can follow.

---

## Review Dimensions

---

### Dimension 27: Rust Idioms, Ownership & Async Correctness
*Matsakis, Gjengset*

| Hazard | What to look for |
|--------|-----------------|
| **`unwrap()` / `expect()` in non-test code** | Every one is a panic in production. `expect("...")` without a comment explaining why it cannot fail is the smell. Use `?` or pattern-match the error. |
| **`unsafe` without `// SAFETY:` comment** | An `unsafe` block with no explanation of the invariants being upheld. The block becomes a maintenance trap — readers can't verify it stays sound. |
| **`unsafe impl Send` / `Sync`** | Manual `Send`/`Sync` implementations without a documented argument for soundness. The compiler trusts you; data races result if you're wrong. |
| **Ignored `Result` via `let _ =`** | `let _ = file.write_all(...)` — silently discards I/O errors. Either handle, propagate via `?`, or document why discard is correct. |
| **Missing `#[must_use]` on result-like return** | A function returning a builder, a future, or a guard that callers might forget to consume. Add `#[must_use]` so the compiler warns. |
| **`Arc<Mutex<T>>` reflex** | Reaching for `Arc<Mutex<T>>` where a channel (`mpsc`/`broadcast`), `RwLock`, atomic, or a single-writer ownership pattern would express the intent better. |
| **`std::sync::Mutex` held across `.await`** | Blocks the async runtime thread. Use `tokio::sync::Mutex` for locks held across await points; `std::sync::Mutex` is fine when not. |
| **Blocking call inside `async fn`** | `std::fs::read`, `reqwest::blocking`, `thread::sleep`, CPU-bound work — all freeze the executor thread. Use the async equivalent or `spawn_blocking`. |
| **Future created but not awaited or spawned** | `async fn` called as a statement (`do_work();` where it should be `do_work().await;`). The future is constructed and dropped. |
| **State change followed by `.await` without RAII** | Acquired a resource, mutated state, then awaited — if the future is dropped, the cleanup never runs. Wrap in a guard whose `Drop` does the cleanup. |
| **`clone()` to escape the borrow checker** | `let x = expensive.clone();` because borrowing was inconvenient — particularly in loops or hot paths. Restructure to borrow, or accept the cost deliberately. |
| **`to_string()` / `String::from(...)` in hot paths** | Allocating to compare or pass a string when `&str` would do. `&str` accepts `&String` via deref coercion — no allocation needed. |
| **`Box<dyn Error>` in library APIs** | Public library functions returning `Box<dyn Error>` deny callers the ability to match on specific failures. Define an error enum with `thiserror`; reserve `anyhow` for application/bin layers. |
| **Errors that swallow context** | `?` chains that lose the chain of causation. Use `.context("...")` (anyhow) or `#[source]` (thiserror) so the cause survives. |
| **Lifetimes that should be elided** | `fn foo<'a>(s: &'a str) -> &'a str` where the compiler would elide both. Noise without value. Conversely, elided lifetimes that hide a non-obvious relationship readers need to see. |
| **Trait object where generics would do** | `Box<dyn Trait>` in a hot path where the concrete type is known at the call site. Generic over `T: Trait` avoids the indirection. |
| **`Vec` allocated in a loop** | Building a `Vec` inside a loop iteration when it could be hoisted, or collecting into a `Vec` when an iterator would suffice for the downstream consumer. |
| **Iterator chain rewritten as indexed loop** | `for i in 0..v.len() { ... v[i] ... }` — defeats bounds-check elision and obscures intent. Use `iter()` / `iter_mut()` / `enumerate()`. |
| **Panic-by-indexing in non-test code** | `v[idx]` where `idx` comes from external input or computation. Use `.get(idx)` and handle `None`. |
| **`pub` on items that should be `pub(crate)`** | Public visibility on items only used within the crate. Every `pub` is API surface. |
| **Cargo features that aren't additive** | Features that disable functionality, or whose combinations don't compose. Features must be additive — enabling one cannot break another consumer. |
| **`tokio::spawn` of a future that borrows non-`'static`** | Spawned tasks require `'static` futures. Code that fights this by `Arc`-wrapping everything often wants `tokio::task::spawn_blocking` or a scoped task instead. |
| **`drop(guard)` for ordering** | Explicit `drop()` of a lock guard to control scope. Usually a sign the scope should be a block (`{ ... }`) instead — the intent is clearer. |

Matsakis's design question: for every `.await` in this code, can you state what happens to in-progress state if the future is dropped at that point? Gjengset's: for every `unwrap()`, can you state the invariant that makes it sound?

## Python Panel

*Active when `app/**/*.py` or `tests/**/*.py` files are in scope.*

- **Raymond Hettinger** — CPython core developer; idiomatic Python, stdlib-first design
- **David Beazley** — *Python Cookbook*, *Python Essential Reference*; Python internals, asyncio architecture, coroutine lifecycle, CPython execution model

Beazley's positions complement Hettinger's idiom focus with a deeper machinery lens. Where Hettinger asks "is there a stdlib primitive for this?", Beazley asks "does this correctly model how Python's async machinery actually works?"

**Beazley's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Understand the event loop** | asyncio is not threads. The event loop runs one coroutine at a time; `await` is a voluntary yield. Code written as if coroutines run in parallel (without `await` separating them) is correct by accident. Code with compound operations across `await` is a race waiting to be noticed. |
| **`asyncio.to_thread` is a thread boundary** | Objects passed into or out of `asyncio.to_thread` cross from the event loop's single-threaded world into a real thread. They need locking or must be immutable. The return value is awaited back in the event loop — it's safe. The arguments are not. |
| **Generator protocol underlies everything** | `async def` functions are generators that yield `Future` objects. Understanding this resolves many "why does this behave unexpectedly" questions: cancellation, exception propagation through `await`, and why `asyncio.CancelledError` should not be caught silently. |
| **Task cancellation must be handled** | An `asyncio.Task` cancelled while awaiting will raise `CancelledError` at the `await` point. Code that catches broad exceptions (`except Exception`) without re-raising `CancelledError` is broken — cancellation propagation stops and the task appears to hang. |
| **`asyncio.gather` failure semantics** | When one coroutine in `gather` raises, the others are not cancelled by default. If the caller doesn't handle this, partially-completed operations can leave state inconsistent. Use `return_exceptions=True` deliberately, or use a `TaskGroup`. |

*Synthesis with Hettinger:* Hettinger's idioms apply to async code too — use `async for`, `async with`, `anyio`/`asyncio` primitives over manual coroutine management. But Beazley's machinery understanding is the lens that catches the subtle correctness bugs idiom can't surface.

---

## Review Dimensions

---

### Dimension 10: Pythonic Design
*Hettinger*

- **Stdlib first**: reimplementing `Counter`, `defaultdict`, `chain`, `islice`, `lru_cache`?
- **Iteration idioms**: `enumerate` over `range(len(...))`? `zip` over index-synchronized loops?
- **Comprehension appropriateness**: used where they improve clarity, extracted where they don't?
- **EAFP vs LBYL**: `try/except` where checking-then-acting would introduce a race?
- **Type annotation completeness**: all public functions fully annotated?
- **`dataclass`/`NamedTuple` over raw dicts** for structured data?
- **Context managers** for all resource management?

---

### Dimension 11: Async & Python Internals
*Beazley, Goetz*

| Hazard | What to look for |
|--------|-----------------|
| **Compound actions across `await`** | Check-then-act or read-modify-write with an `await` between the check and the act — another coroutine can run during the await and invalidate the check. |
| **Unguarded shared mutable state** | A mutable object accessed from more than one coroutine or thread without a lock or queue. |
| **`asyncio.to_thread` boundary crossings** | Mutable objects passed as arguments to `asyncio.to_thread` cross into a real thread and need locking or must be immutable. |
| **Silent `CancelledError` swallowing** | `except Exception` that catches `CancelledError` without re-raising stops cancellation propagation — the task appears to hang. |
| **`asyncio.gather` failure semantics** | When one coroutine in `gather` raises, others continue by default. Partial completion leaves state inconsistent unless `return_exceptions=True` is used deliberately. |
| **Safe publication** | An object initialized in one coroutine/thread published to shared state before fully initialized. |

Goetz's design-level questions: can you name, for every shared mutable field, which lock or discipline protects it? Is thread confinement used where possible?

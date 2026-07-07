## JVM (Java & Kotlin) Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Brian Goetz** — Java language architect; *Java Concurrency in Practice*; JMM, virtual threads, the disciplined concurrency model
- **Joshua Bloch** — *Effective Java*; API design, immutability, the cost of inheritance, the discipline that distinguishes good Java from bad

**Goetz's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Visibility and atomicity are separate problems** | `volatile` gives visibility but not atomicity — `count++` on a volatile field is still racy. `synchronized` gives both. `Atomic*` types give both for single operations. Knowing which guarantee you need is the discipline. |
| **Immutability is the simplest path to thread safety** | An immutable object can be shared across threads without synchronization. Most "thread safety bugs" disappear when the offending object becomes immutable. Build immutable types by default; reach for mutability with a reason. |
| **Never swallow `InterruptedException`** | Catching `InterruptedException` and continuing breaks the cancellation contract. Either propagate the exception or restore the interrupt flag (`Thread.currentThread().interrupt()`) and bail. |
| **Virtual threads change scaling, not correctness** | Virtual threads (Project Loom) let you write blocking code at high concurrency. They do not fix data races, lock contention, or `ThreadLocal` misuse. Pinning issues (holding a monitor across a blocking call) regress to platform-thread behavior. |
| **`CompletableFuture` without an executor uses the common ForkJoinPool** | `supplyAsync(...)` without an explicit `Executor` runs on the shared pool — fine for CPU work, disaster for blocking I/O. Always pass an executor sized for the work. |

**Bloch's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Favor composition over inheritance** | Inheritance breaks encapsulation: subclasses depend on implementation details of superclasses across version boundaries. Use composition + delegation unless there's a true is-a relationship and both classes are under your control. |
| **Minimize mutability** | Make classes immutable by default. Make every field `final` unless you have a reason for it not to be. Provide builders for multi-parameter construction. |
| **`equals`/`hashCode` come as a pair** | Override one, override both. Honor the contract: equal objects must have equal hash codes; equality is symmetric, transitive, reflexive, consistent. Records (Java) and data classes (Kotlin) get this for free — prefer them. |
| **`Optional` is for return types, not fields or parameters** | `Optional<T>` was introduced for return values, to make absence explicit. As a field type it's an unnecessary heap object; as a parameter type it pushes the absence check into the caller. Return `Optional`; accept `T` and overload. |
| **Use enums for type-safe constants** | A set of `public static final int` constants is a refactor waiting to happen. Enums get type safety, namespacing, methods, and `switch` exhaustiveness checking. |
| **Document threading expectations** | Every shared mutable field should have a Javadoc tag or comment naming the lock that protects it (`@GuardedBy`). Undocumented threading discipline is undiscoverable threading discipline. |

*Synthesis:* Goetz evaluates whether the code is correct under the Java Memory Model — visibility, atomicity, cancellation propagation, thread confinement. Bloch evaluates whether the API design is one a downstream user can use without consulting source — immutability, contract honesty, clear types. JVM code can be thread-safe and unusable, or beautifully designed and full of races.

---

## Review Dimensions

---

### Dimension 28: JVM Concurrency, API Design & Idioms
*Goetz, Bloch*

| Hazard | What to look for |
|--------|-----------------|
| **`volatile` used for compound operations** | `volatile int count; count++;` — visibility without atomicity. Use `AtomicInteger`, `LongAdder`, or `synchronized`. |
| **Lock held across blocking I/O** | `synchronized` block that calls into network, disk, or a queue. Lock duration is now I/O duration. |
| **Swallowed `InterruptedException`** | `catch (InterruptedException e) { /* ignore */ }` or logged-and-continued without `Thread.currentThread().interrupt()`. Breaks cancellation. |
| **`synchronized(this)` or `synchronized(SomeClass.class)`** | Publicly lockable monitor — any caller can deadlock you. Use a private `final Object lock = new Object();`. |
| **`CompletableFuture` without explicit executor** | `supplyAsync(...)` / `thenApplyAsync(...)` without an `Executor` argument — shared `ForkJoinPool.commonPool()` for everything. Disaster if the work blocks. |
| **`ThreadLocal` without cleanup** | `ThreadLocal` set in a request scope but never `remove()`d. On a thread pool (every server), the value leaks into the next request. |
| **Mutable static field** | `public static List<X> items = new ArrayList<>();` — shared mutable state across the JVM with no thread safety. |
| **Returning mutable collection** | A getter returning the internal `List` / `Map` directly. Callers mutate; invariants break. Return `List.copyOf(...)` or `Collections.unmodifiableList(...)`. |
| **Inheritance for code reuse, not type hierarchy** | `class UserService extends AbstractService` where the relationship is "shares some code." Use composition. |
| **`equals` without `hashCode` (or vice versa)** | A class with one but not the other. Breaks every hash-based collection silently. |
| **`Optional<T>` as field or parameter** | `private Optional<String> name;` or `void f(Optional<String> name)`. Use nullable + `@Nullable`, or overload. |
| **Returning `null` for a missing value** | Method returns `User getUser(...)` and `null` means "not found." Use `Optional<User>` or throw. |
| **`catch (Exception e)` or `catch (Throwable t)`** | Overbroad catch — swallows `RuntimeException` you didn't anticipate; `Throwable` even catches `Error` (OOM). Catch the specific type. |
| **Spring `@Transactional` on a self-invoked method** | `this.doWork()` from another method in the same bean bypasses the proxy — `@Transactional` does not apply. Inject the bean by interface, or split classes. |
| **Spring field injection** | `@Autowired private FooService foo;` — hides dependencies, untestable without reflection, encourages cyclic dependencies. Use constructor injection. |
| **Lazy loading outside the persistence session** | JPA entity returned from a service; controller accesses a lazy field — `LazyInitializationException` or N+1 fetch. Fetch what's needed inside the session boundary. |
| **`Date` / `Calendar` for new code** | Mutable, timezone-confused legacy types. Use `java.time` (`Instant`, `LocalDate`, `ZonedDateTime`). |
| **`parallelStream()` without measurement** | Splits onto the common ForkJoinPool. Contends with every other parallel stream in the JVM. Often slower than serial. Benchmark before using. |
| **Kotlin `!!` non-null assert** | `someValue!!` — equivalent to `unwrap()`. Each one is a NPE in disguise. Use `?:`, `?.let { }`, or a real check. |
| **Kotlin `lateinit` for what should be `val`** | `lateinit var x: Foo` when constructor injection would do. `lateinit` exists for framework boundaries (Spring fields, Android `onCreate`); not for general use. |
| **Kotlin `runBlocking` in production code** | `runBlocking { ... }` inside a suspend function or a request path — defeats coroutines. Only acceptable at the very edge (main, tests). |
| **Kotlin `GlobalScope.launch`** | Unstructured concurrency. Coroutine outlives the caller; cancellation is broken. Use a scoped `CoroutineScope`. |
| **Kotlin data class with `var`** | `data class User(var name: String)` — generated `equals`/`hashCode` on mutable fields; the object's hash code can change while it lives in a `HashMap`. |
| **Throwing from a destructor (Java: `finalize` / `AutoCloseable.close`)** | `close()` throwing while another exception is being thrown loses the original. Suppress carefully (try-with-resources handles this). |
| **`@SuppressWarnings("unchecked")` without comment** | Every suppression deserves a one-line justification of why the unchecked cast is sound. |

Goetz's design question: for every shared mutable field, can you name the lock or discipline that protects it? Bloch's: can a caller use this class correctly from the public Javadoc alone, without reading the source?

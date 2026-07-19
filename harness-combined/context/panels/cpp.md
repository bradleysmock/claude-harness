## C / C++ Panel

*Activation is governed by the trigger table in `context/panels/triggers.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Bjarne Stroustrup** — C++ creator; type safety as the primary tool, RAII, "within C++ there is a smaller, cleaner language struggling to get out"
- **Herb Sutter** — ISO C++ standards committee chair; *Exceptional C++*, C++ Core Guidelines, GotW; modern C++ discipline

**Stroustrup's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **RAII is the resource discipline** | Every resource — memory, file, lock, socket, GPU buffer — should be owned by an object whose destructor releases it. Manual `new`/`delete`, `fopen`/`fclose`, `lock`/`unlock` are bugs waiting for a missed code path. |
| **Type safety over runtime checking** | Encode invariants in the type system. A function taking `Email` cannot be called with an arbitrary `std::string`. The compiler enforces what would otherwise be a runtime check that gets skipped. |
| **Prefer references over pointers when lifetime allows** | A `T&` parameter cannot be null; a `T*` can. Use references for "borrowed and present"; pointers for "borrowed and possibly absent" or "owned." Smart pointers replace raw owning pointers. |
| **Don't pay for what you don't use** | The language gives you control over allocation, dispatch, copying. Use it: `constexpr` for compile-time work, `inline`/templates for zero-cost abstraction, `noexcept` for codegen and exception-safety guarantees. |
| **The standard library is the baseline** | Reimplementing `std::vector`, `std::optional`, `std::variant`, `std::span` is almost always wrong. The stdlib versions are tested by everyone, optimized by compiler authors, and known to readers. |

**Sutter's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Rule of zero, then rule of five** | If a class doesn't manage a resource directly, write none of the special member functions — let the compiler generate them. If you define one of destructor / copy / move, you must define (or `= delete` / `= default`) all five. |
| **`std::unique_ptr` by default; `shared_ptr` only when sharing** | `unique_ptr` is zero-overhead; `shared_ptr` carries an atomic ref count. Reaching for `shared_ptr` because "I'm not sure who owns it" is a design smell — figure out the ownership. |
| **Never raw `new` / `delete` in modern C++** | `std::make_unique<T>(...)` for owning; container types (`std::vector`, `std::string`) for buffers. Raw `new` is for implementing your own RAII type, not for application code. |
| **Use after move is valid but unspecified** | A moved-from object can be assigned to or destroyed, but its contents are unspecified. Code that reads a moved-from value is reading garbage that compiles cleanly. |
| **Exceptions for exceptional conditions; not for control flow** | Throw for errors that the immediate caller cannot reasonably handle. For "user typed a wrong value," return a `std::optional` or `std::expected`. |
| **`const` everything that doesn't need to change** | `const` parameters, `const` methods, `const` locals. Each `const` is a constraint the compiler enforces and a hint to the reader. |
| **`std::span` / `gsl::span` over pointer + length** | Two parameters that must be kept in sync are a bug factory. `span` packages them; bounds are visible. |

*Synthesis:* Stroustrup evaluates whether the code uses the language's safety primitives — RAII, types, references — instead of fighting them. Sutter evaluates whether the code reflects modern C++ idioms — smart pointers over raw, algorithms over loops, `const` discipline, the Core Guidelines. C++ written like 1998 still compiles, but every line is a hazard the language has since provided tools to eliminate.

---

## Review Dimensions

---

### Dimension 30: C/C++ Memory Safety, Modern Idioms & Undefined Behavior
*Stroustrup, Sutter*

#### Memory safety (C and C++)

| Hazard | What to look for |
|--------|-----------------|
| **Buffer overflow APIs** | `strcpy`, `strcat`, `sprintf`, `gets`, `scanf("%s", ...)` — unbounded writes. Use `snprintf`, `strncpy` *with* manual null-termination, or C++ `std::string`. |
| **`strncpy` assumed to null-terminate** | If the source is longer than `n`, no null terminator is written. Always set `dst[n-1] = '\0'` after, or use `strlcpy` where available. |
| **`malloc` return not checked for NULL** | `int* p = malloc(n * sizeof(int)); p[0] = 0;` — segfault if allocation failed. Check or use a wrapper that aborts on failure. |
| **Integer overflow / signed wrap** | Signed integer overflow is undefined behavior in C and C++. `int n = x + y;` where `x + y` overflows is a UB compiler bug magnet (loops vanish, bounds checks evaporate). Use `__builtin_add_overflow`, `<stdckdint.h>` (C23), or wider types. |
| **Format string from user input** | `printf(user_input)` or `printf(buf)` where `buf` is user-controlled — format-string vulnerability. Always `printf("%s", user_input)`. |
| **Use after free / double free** | Pointer freed then dereferenced; pointer freed twice. Set to `NULL` after `free`, or use RAII (C++) or attribute-cleanup (gcc/clang C extension). |
| **Uninitialized read** | `int x; if (cond) x = 1; use(x);` — `x` is indeterminate on the `else` path. UB on use. |
| **`memcpy` / `memmove` size confusion** | `memcpy(dst, src, sizeof(src))` where `src` is a pointer — copies `sizeof(void*)` bytes, not the buffer size. |
| **`sizeof` on array decayed to pointer** | `void f(int arr[]) { size_t n = sizeof(arr) / sizeof(arr[0]); }` — `arr` is a pointer here; `sizeof` is the pointer size. Pass length explicitly or use `std::span`. |
| **Signed/unsigned comparison** | `if (i < size())` where `i` is `int` and `size()` returns `size_t`. Negative `i` converts to large unsigned. Compile with `-Wsign-compare`. |

#### Modern C++ idiom (C++ only)

| Hazard | What to look for |
|--------|-----------------|
| **Raw `new` / `delete`** | `T* p = new T(...); ... delete p;` — leak on any exception. Use `std::make_unique<T>(...)`. |
| **Raw owning pointer** | A class field `T*` that the class deletes. Use `std::unique_ptr<T>`. Member raw pointers should be non-owning. |
| **Missing rule-of-five (or zero)** | Class defines a destructor (or copy constructor, or move constructor, ...) but not all five. Implicit moves/copies do the wrong thing silently. Either define all (or `= default` / `= delete`), or define none. |
| **Polymorphic base without virtual destructor** | `class Base { ... };` used as `delete static_cast<Base*>(derived_ptr)` — non-virtual destructor → only `Base`'s destructor runs → derived parts leak. Mark destructors `virtual` in polymorphic bases. |
| **Slicing on copy** | `Base b = derived;` — derived parts are sliced off. Pass polymorphic types by reference or pointer, never by value. |
| **Catch by value (slicing the exception)** | `catch (std::exception e)` — slices any `std::runtime_error` to `std::exception`. Always `catch (const std::exception& e)`. |
| **Throwing from destructor** | If a destructor throws while another exception is propagating, `std::terminate` is called. Destructors should be `noexcept` (the default since C++11). |
| **`std::move` of `const`** | `std::move(const_value)` returns `const T&&`, which binds to copy constructors, not move constructors — silent copy. Compiles, does the wrong thing. |
| **Use after move** | `auto x = std::move(y); use(y);` — `y` is in a valid-but-unspecified state. Reading it is a bug. |
| **Returning reference to local** | `const T& f() { T x; return x; }` — dangling. Compilers warn; the warning is correct. |
| **Dangling `std::string_view` / `std::span`** | `std::string_view sv = std::string("temp");` — temporary destroyed at end of statement; `sv` dangles. Same for `span` over a temporary. |
| **`shared_ptr` cycle** | `A` holds `shared_ptr<B>`; `B` holds `shared_ptr<A>`. Neither ref count reaches zero. Use `weak_ptr` for the back-reference. |
| **Lambda capturing by reference outliving scope** | `[&]` lambda stored, passed to async work, executed after the captures' lifetime ends. Capture by value or by `shared_ptr` for async work. |
| **Iterator invalidation after container mutation** | `for (auto it = v.begin(); it != v.end(); ++it) { if (...) v.erase(it); }` — `it` is invalidated. Use the erase-remove idiom or the iterator returned by `erase`. |
| **`auto` vs `auto&` vs `const auto&`** | `auto x = container.front();` copies. `auto&` borrows. In ranged-for over an expensive type, `for (const auto& x : xs)` is usually what you wanted. |
| **C-style cast** | `(int)x` — bypasses type safety; could be `static_cast`, `reinterpret_cast`, `const_cast`, or any combination silently. Use the named cast that expresses intent. |
| **ODR violation** | The same inline function or template defined differently across translation units. Compiles, links, runs unpredictably. |
| **Static initialization order fiasco** | Non-local static `A` references non-local static `B` in another TU. Their initialization order is unspecified. Use Meyers singletons (`static T& get() { static T t; return t; }`). |
| **Reimplementing stdlib** | Hand-rolled `vector`, `string_view`, `optional`, `variant`, `span`, `unique_ptr`. The stdlib version is tested everywhere and known to readers. |
| **`reinterpret_cast` / type punning** | Casting `T*` to `U*` and reading — almost always UB unless `U` is `std::byte`, `char`, or `unsigned char`. Use `std::memcpy` for type punning; `std::bit_cast` (C++20) when applicable. |
| **`const_cast` to mutate** | `const_cast<T*>(p)` then writing through it. If the original object was actually `const`, UB. Almost never the right answer — fix the design. |

#### Build & toolchain

| Hazard | What to look for |
|--------|-----------------|
| **Compiler warnings disabled or ignored** | `-w`, `#pragma warning(disable: ...)` without justification. Build cleanly at `-Wall -Wextra -Wpedantic` (gcc/clang) or `/W4` (MSVC). |
| **No sanitizer in CI** | A codebase without an ASan/UBSan/TSan build target. These catch the most expensive bugs early. |
| **CMake `file(GLOB)` for sources** | Changes to source list don't trigger reconfigure. List sources explicitly. |
| **Missing `-fno-strict-aliasing` discipline** | Code that type-puns via pointer cast and relies on `-fno-strict-aliasing` to make it work. Use `memcpy` or `std::bit_cast`. |

Stroustrup's design question: for every resource this code acquires, is there an RAII object that releases it on every exit path — including exceptions? Sutter's: if you compile this with `-Wall -Wextra` and run it under ASan + UBSan, does it pass clean?

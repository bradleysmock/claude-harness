## Angular Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md`. TypeScript-level concerns (type discipline, async correctness, ESM/CJS) defer to the TypeScript/JS panel; this panel covers Angular-specific machinery — change detection, signals, dependency injection, RxJS lifecycle, standalone components, and the migration surface between legacy and modern Angular.*

- **Minko Gechev** — Angular framework team lead; signals, standalone components, change detection, the post-NgModule era; canonical voice on what "modern Angular" actually means
- **Ben Lesh** — RxJS lead maintainer; observable lifecycle, subscription management, hot vs. cold semantics, the operator vocabulary that Angular codebases live and die by

**Gechev's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Signals are the reactivity primitive going forward** | Signals (`signal`, `computed`, `effect`) replace `BehaviorSubject` + `async` pipe for component-local reactive state in Angular 17+. They give automatic dependency tracking, glitch-free updates, and a path away from zone.js. New code defaults to signals; converting existing observables is a project, not a prerequisite. |
| **Change detection is the cost; reduce its surface** | The default change detection strategy runs across the entire component tree on every async event (every click, every HTTP response, every `setTimeout`). `OnPush` confines a subtree to running only on input change, observable emission via `async`, or signal read. Production Angular apps live on `OnPush`; the default strategy is for prototypes. |
| **Standalone components are the default** | NgModules are a 2016 design that the team has been migrating away from since 2022. Standalone components, `provideRouter`, `provideHttpClient`, and `bootstrapApplication` replace the module-based bootstrap and lazy-loading machinery. New code is standalone; mixing standalone with NgModule-based code works but adds cognitive load. |
| **Dependency injection is the framework's superpower; don't fight it** | `inject()` inside an injection context is the modern access pattern. DI gives testability (override `providers` in the test bed), tree-shakability (`providedIn: 'root'`), and a hierarchical scope model. Reaching past DI to `new MyService()` or static singletons forfeits all three. |
| **Templates are a first-class API** | `@if`, `@for`, `@switch`, `@defer` (Angular 17+) replace `*ngIf`, `*ngFor`, `*ngSwitch`. The new control flow is faster (no directive resolution), better-typed, and supports `@empty` / `@loading` / `@placeholder` blocks that the old syntax couldn't express. New templates use the block syntax; legacy templates migrate when touched. |
| **Reactivity boundaries: inputs in, outputs out, signals inside** | Component public surface is `input()` (signal-backed inputs replacing `@Input()`), `output()` (replacing `@Output()` + `EventEmitter`), `model()` for two-way. Internal state is signals. Treat the component boundary as a typed reactive contract — not a place to spray observables and side effects. |

**Lesh's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Observables are lazy; subscriptions are everything** | An observable does nothing until subscribed. Each `.subscribe()` is a *new* execution of the source pipeline. `httpClient.get(...)` subscribed twice makes two HTTP requests. Multicasting (`shareReplay`, `share`) is how you make one execution serve many consumers. |
| **Every subscription needs a teardown path** | A `.subscribe()` that outlives its component leaks every closure it captured. Use `takeUntilDestroyed()` (Angular 16+) inside an injection context, the `async` pipe (which subscribes and unsubscribes for you), or explicit `takeUntil(destroy$)` patterns. Manual `.unsubscribe()` is a maintenance trap. |
| **Hot vs. cold determines correctness** | Cold observables (HTTP, `interval`, `of`) restart per subscriber. Hot observables (`Subject`, `BehaviorSubject`, multicasted streams) share emissions. Code that treats `BehaviorSubject` as if it were cold (or HTTP as if it were hot) is racing or duplicating. |
| **The operator vocabulary is the API** | `switchMap` cancels prior inner observables — right for typeahead search. `mergeMap` runs them concurrently — right for fire-and-forget. `concatMap` queues them — right for ordered writes. `exhaustMap` ignores while busy — right for login submits. Picking the wrong one is a class of bug RxJS won't catch for you. |
| **Errors are values; the stream terminates on `error`** | An unhandled `error` notification terminates the observable for all subscribers — including the next emission you expected. Use `catchError` at the boundary where the error becomes recoverable; `retry` / `retryWhen` for transient failures with explicit policy. |
| **Subjects are escape valves, not the design** | `Subject` and `BehaviorSubject` are imperative bridges into reactive code. They're correct for genuine imperative→reactive boundaries (DOM events that no Angular directive captures, third-party callbacks). Reaching for them inside a service to "share state between components" is usually a signal opportunity in disguise. |

*Synthesis:* Gechev evaluates whether the code embraces modern Angular's framework primitives — signals, standalone components, `inject()`, the new control flow, `OnPush` — or whether it's fighting the framework with NgModule-era patterns. Lesh evaluates whether the RxJS layer is *correct* — subscriptions teardown, hot/cold understood, operator choice intentional, errors handled at the right boundary. An Angular app can be perfectly modern-looking and leak subscriptions on every navigation; or RxJS-correct and stuck in 2018 idioms that recompile slower and trigger change-detection storms. The migration from "old Angular" to "new Angular" is the central tension in most production codebases — flag legacy patterns where they cause bugs, leave them where they're stable.

---

## Review Dimensions

---

### Dimension 35: Modern Angular Idioms & Change Detection
*Gechev*

| Hazard | What to look for |
|--------|-----------------|
| **Default change detection on a non-trivial component** | Component without `changeDetection: ChangeDetectionStrategy.OnPush`. Every async event in the app re-checks this subtree. In a large app, the default strategy is a performance bug shipped on day one. |
| **`@Input()` with mutable object** | Parent mutates a property of an object passed as `@Input`. Reference is unchanged → `OnPush` doesn't fire → child shows stale data. Use signal inputs (`input()`) or immutable updates. |
| **NgModule for new code** | New feature added as an `NgModule` instead of standalone components + `provideXxx()` functions. Migrating later is a refactor; starting modern is free. |
| **`*ngIf` / `*ngFor` in new templates** | New templates using structural directives instead of `@if` / `@for` / `@switch`. Block syntax is faster, better-typed, and supports cases the directive syntax can't (`@empty`, `@defer`). |
| **`@ViewChild` / `@ContentChild` decorators in new code** | Replaced by `viewChild()` / `contentChild()` (signal-based) since Angular 17.2. Decorator forms are still supported but the signal form composes with the new reactivity model. |
| **Two-way binding via manual `@Input()` + `@Output()`** | `[(value)]` implemented as `[value]` + `(valueChange)` with manual sync logic. Use `model()` for two-way signal-backed binding. |
| **`new Service()` instead of `inject()`** | A service instantiated directly with `new` — bypasses DI, breaks testability via `TestBed`, can't be overridden in tests or environments. |
| **`providedIn: 'root'` for something that should be scoped** | Service registered globally that maintains per-feature or per-route state. State leaks across navigations. Scope to the lazy route or feature provider. |
| **Component imports an entire library module** | `imports: [CommonModule, FormsModule, ReactiveFormsModule, ...]` when only `NgIf` and `NgClass` (or the `@if` block) are used. Standalone-components era: import the specific directives. |
| **Signal updates inside `computed()`** | A `computed()` that calls `set()` on another signal — creates a cycle the framework will warn about, but the design is wrong. `computed` is pure derivation; side effects belong in `effect()`. |
| **`effect()` for derivation** | An `effect()` that reads signals and writes to another signal — should be `computed()`. `effect()` is for side effects (logging, DOM imperative work, calling out to non-reactive APIs). |
| **`async` pipe in a `OnPush` component reading a hot observable** | Works, but stale: `async` triggers change detection on emission, fine for cold; for hot observables already in flight, the initial value may be missed. Use `toSignal()` (Angular 16.1+) to bridge. |
| **Forms: template-driven mixed with reactive in one component** | `ngModel` and `FormGroup` in the same form. Pick one model; mixing produces dual sources of truth that drift. |
| **`HttpClient` interceptors as classes when functions work** | Functional interceptors (`HttpInterceptorFn`) are the post-15 idiom. Class-based interceptors with `HTTP_INTERCEPTORS` multi-provider are the migration target, not the starting point. |
| **`bootstrapModule` instead of `bootstrapApplication`** | Application bootstrap still going through `AppModule` instead of standalone bootstrap. The migration path is well-documented; new apps shouldn't start there. |
| **Zone.js relied on for unrelated async** | `setTimeout` / `Promise.then` expected to "just trigger change detection" — works because of zone.js patching, but coupling business logic to that patching is fragile. Use `NgZone.run()` deliberately or signals. |
| **Lazy loading by route module instead of by route** | `loadChildren: () => import('./feature.module').then(m => m.FeatureModule)` instead of `loadComponent: () => import(...)` for component-level lazy loading. |
| **`@defer` block without trigger** | Deferred view declared but no `on viewport` / `on idle` / `on hover` / `when condition` trigger. Block never loads, or loads immediately, both probably wrong. |

---

### Dimension 36: RxJS Discipline (Subscriptions, Operators, Errors)
*Lesh*

| Hazard | What to look for |
|--------|-----------------|
| **`.subscribe()` without teardown** | `.subscribe(handler)` called outside of an `async` pipe, without `takeUntilDestroyed()` / `takeUntil(destroy$)`, without storing the `Subscription` for cleanup. Each navigation leaks the closure and every reference it captures. |
| **Manual `OnDestroy` boilerplate when `takeUntilDestroyed` exists** | Component declaring `destroy$ = new Subject<void>()` + `ngOnDestroy { destroy$.next(); destroy$.complete(); }` in modern Angular. `takeUntilDestroyed()` does this in one line within an injection context. |
| **Multiple subscriptions to a cold HTTP observable** | `obs$ = http.get(...)` subscribed-to in `async` pipe in template *and* `.subscribe()` in controller. Two HTTP requests. Add `shareReplay({ bufferSize: 1, refCount: true })`. |
| **`shareReplay` without `refCount`** | `shareReplay(1)` (or `shareReplay({ bufferSize: 1 })` without `refCount: true`) — keeps the source subscribed forever after the last consumer unsubscribes. Memory leak that survives navigation. |
| **`mergeMap` where `switchMap` was wanted** | Typeahead search using `mergeMap` — every keystroke fires a request, responses arrive out of order, the last-typed query may not be the last-displayed result. `switchMap` cancels in-flight on new input. |
| **`switchMap` where order matters** | Sequential mutations (`POST /save`, `POST /save` from rapid clicks) under `switchMap` cancel earlier writes. Use `concatMap` for ordered writes or `exhaustMap` to ignore-while-busy. |
| **`subscribe(next, error)` callback form** | Three-argument `subscribe(next, error, complete)` is deprecated. Use the observer-object form `subscribe({ next, error, complete })`. |
| **No `catchError` boundary** | An observable chain where any operator can error and there's no `catchError` between the source and the consumer. The stream terminates; no further emissions; UI freezes mid-state. |
| **`catchError` swallowing without rethrow or recovery** | `catchError(() => of(null))` returning a stand-in value with no logging, no telemetry, no user feedback. The error is invisible. Either return a domain-meaningful "error" value the UI renders, or re-throw via `throwError` for the boundary above. |
| **`retry()` without limit or backoff** | `retry()` / `retryWhen()` retrying a failed observable with no max attempts, no backoff, no transient-vs-terminal distinction. A persistent 500 retried at full speed becomes a self-DoS. |
| **`Subject` used as state store** | A `BehaviorSubject` in a service used to hold and broadcast component state. Often a signal (`signal()`) is the better fit — synchronous read, no subscription, no teardown, signals into templates without `async`. |
| **`new Subject()` exposed publicly** | A service exporting `Subject` as `public subject$ = new Subject()`. Consumers can call `.next()` on it from anywhere — the API becomes "anyone can publish." Expose `.asObservable()` from a private subject. |
| **`firstValueFrom` / `lastValueFrom` without timeout** | Awaiting an observable that may never complete (a stream of router events, a Subject that only fires on user action). Wrap in `timeout(...)` or design the consumer to subscribe. |
| **Hot observable consumed as if cold** | Code subscribing to a `Subject` and expecting the prior value — misses emissions that happened before subscription. If you need the latest value, use `BehaviorSubject` or `ReplaySubject`. |
| **`tap` for side effects that should be `subscribe`** | `tap(value => this.state = value)` writing component state. `tap` is for in-stream debugging or read-only side effects; state writes belong in `subscribe()` (with teardown) or the `async` pipe. |
| **`toPromise()` in new code** | Deprecated and removed in RxJS 8. Use `firstValueFrom` or `lastValueFrom` with explicit timeout. |
| **Imports from `'rxjs/operators'`** | Pre-RxJS 7 import path. All operators are now imported from `'rxjs'` directly. Old path still works but signals codebase age. |
| **Forms valueChanges without `distinctUntilChanged` for derived calcs** | A reactive form's `valueChanges` observable subscribed to drive expensive recomputation, without `distinctUntilChanged` — recomputes on every keystroke including no-op changes (focus blur, programmatic resets). |

Gechev's design question: for every `NgModule`, decorator-based `@ViewChild`, `*ngIf`, and direct `new Service()` in this code, what blocks migrating it to the modern equivalent? If the answer is "nothing, we just haven't" — that's a tracked debt item, not a defensible state.

Lesh's design question: for every `.subscribe()` in this code, can you name what unsubscribes it, and what happens to in-flight emissions if the component is destroyed mid-stream? If "we use `takeUntilDestroyed`" is the answer for some but not others, identify why — usually the inconsistent ones are the leaks.

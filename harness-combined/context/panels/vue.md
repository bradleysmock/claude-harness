## Vue Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md`. TypeScript-level concerns defer to TypeScript/JS; generic UI concerns defer to UI; this panel covers Vue-specific machinery — the reactivity model (Proxy-based fine-grained tracking), the Composition API, Single File Components, `<script setup>` and the macro-driven compiler API, Pinia, and the composable ecosystem.*

- **Evan You** — Vue creator; the reactivity model, Composition API design, the SFC compiler, Vue 3's architecture; canonical voice on what is and isn't reactive and why
- **Anthony Fu** — VueUse, Vite ecosystem, Vue / Nuxt core team; the working voice on modern Vue idioms — `<script setup>`, composables, Pinia, the migration from Vuex/Vue 2 patterns to the 3.x default style

**Evan You's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Reactivity is the primitive; understand what is and isn't reactive** | Vue 3's reactivity is based on `Proxy`: a `ref()` or `reactive()` is observable, a plain object is not. Assigning a plain object into a previously-reactive slot makes the slot non-reactive. Reactivity is fine-grained — only the specific properties read during a render are re-tracked when they change, not the whole object. |
| **`ref` for values; `reactive` for objects you don't pass around** | `ref(0)`, `ref([])`, `ref(obj)` — works for everything, `.value` in script, auto-unwrapped in templates. `reactive({...})` is a `Proxy` over the object — losing the reference (destructuring, returning the proxy from a function) loses reactivity. New code defaults to `ref`; `reactive` is for objects that stay put. |
| **Destructuring a reactive object loses reactivity** | `const { name } = reactive({ name: 'x' })` — `name` is a plain string; mutations to the source no longer track. Use `toRefs(state)` to destructure into refs, or read through the source proxy. This is the most common "why isn't my component updating" bug. |
| **Computed properties cache; methods do not** | A `computed()` re-runs only when its tracked dependencies change. A method called from a template runs on every render. For derived values used in templates, default to `computed`; reach for methods only when the function takes arguments or has side effects (which it shouldn't anyway). |
| **`watch` is for side effects; `computed` is for derivation** | `computed` produces a value; `watch` runs code in response to a change. Code that calls `setSomething()` from inside `computed` is a bug — derivations must be pure. Code that derives a value inside `watch` and pushes it to another ref is `computed` written awkwardly. |
| **The template is compiled** | Templates are not strings interpreted at runtime — they're compiled to render functions at build time. This is what makes the `v-` directives, `<script setup>` macros, and reactivity tracking work together. Implication: macros (`defineProps`, `defineEmits`, `defineModel`, `defineExpose`) are compiler hooks, not runtime functions. They have rules the compiler enforces: top-level, no destructured imports, no conditional invocation. |
| **One-way data flow: props down, events up** | A child mutating a prop is the canonical violation. Vue warns on direct mutation; the workaround patterns (cloning to local state, emitting `update:propName`) exist for a reason. For two-way binding, `defineModel()` (Vue 3.4+) is the supported, type-safe form — not manual prop + emit choreography. |

**Anthony Fu's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **`<script setup>` is the default for new code** | The Options API and `defineComponent({ setup() {...} })` still work, but `<script setup>` is the form Evan and the team optimize for: less boilerplate, better TypeScript inference, top-level `await`, the macro API. New components use it; converting existing Options-API components is a project, not a prerequisite. |
| **Composables are the unit of reuse** | A composable is a function whose name starts with `use`, called inside `setup` (or another composable), returning refs / computeds / functions. It's the replacement for mixins (Vue 2) and the Vue equivalent of React hooks. Composables compose, are independently testable, and unlike mixins don't collide on shared state. |
| **VueUse before custom reactivity** | Most "I need to track X" composables already exist: `useStorage`, `useDebounce`, `useEventListener`, `useIntersectionObserver`, `useMouse`, `useFetch`. Check VueUse before writing custom; the library handles SSR, cleanup, and edge cases the custom version usually doesn't. |
| **Pinia is the canonical store; Vuex is the migration target** | Vuex 4 still works but is in maintenance mode. Pinia is the recommended store: no mutations layer, full TypeScript inference, devtools support, code-splittable. New stores use Pinia; Vuex stores migrate when touched. |
| **Composables must clean up after themselves** | A composable that registers an event listener, starts a timer, opens a connection, or subscribes to something must clean up via `onScopeDispose` (or `onUnmounted` when called from a component). Composables called outside a component setup must run inside an `effectScope` if cleanup matters. |
| **The composable returns refs, not values** | A composable destructured at the call site (`const { value } = useThing()`) where `value` is a plain value loses reactivity at the boundary. Composables return refs / computeds so destructured callers preserve reactivity (`const { count } = useCounter()` keeps `count` as a ref). |
| **Reactive props destructure (Vue 3.5+) over `withDefaults` chains** | The old form `withDefaults(defineProps<...>(), { ... })` works but is verbose. The reactive props destructure form `const { foo = 1, bar = 'x' } = defineProps<...>()` is cleaner and the compiler keeps reactivity. New code defaults to it. |

*Synthesis:* Evan You evaluates whether the code respects Vue's reactivity model — what is tracked, what isn't, where destructuring or reassignment loses reactivity, whether derivations are `computed` and effects are `watch`, whether the template compiler's contract (macros, directives, top-level rules) is honored. Anthony Fu evaluates whether the code embraces modern Vue's idioms — `<script setup>`, composables with proper cleanup, Pinia over Vuex, VueUse before reinvention, `defineModel` for two-way binding, reactive props destructure over verbose `withDefaults`. A Vue codebase can be reactive-correct but stuck in Options-API-with-Vuex 2018 idioms, or fully modern in shape and silently broken because someone destructured a `reactive()` and lost the proxy. Most production Vue bugs are one of: a non-ref value where a ref was expected, a destructured `reactive` losing the proxy, a composable without cleanup, or a `watch`/`computed` written for the wrong purpose.

---

## Review Dimensions

---

### Dimension 39: Vue Reactivity Model & Component Architecture
*Evan You*

| Hazard | What to look for |
|--------|-----------------|
| **Destructured `reactive()` loses reactivity** | `const state = reactive({ count: 0 }); const { count } = state;` — `count` is a snapshot, not a ref. Use `const { count } = toRefs(state)` or read `state.count` directly. |
| **Plain object replacing reactive slot** | `state.user = { name: 'x' }` where `state` is reactive — the new object is wrapped on assignment, OK. But `const data = ref({}); data.value = freshObj` then reading inside templates expects deep tracking that may not be there. Reach for `ref` (wraps deeply) vs `shallowRef` (wraps top-level only) deliberately. |
| **Mutating a prop directly** | `props.user.name = 'x'` inside a child — violates one-way data flow, Vue warns. For local edits, copy to local state; for two-way, use `defineModel()` (Vue 3.4+). |
| **`computed` with side effects** | `const total = computed(() => { someRef.value = ...; return sum })`. Computeds must be pure. Side effects belong in `watch` or `watchEffect`. |
| **`watch` immediate when `watchEffect` would do** | `watch(source, fn, { immediate: true })` reading every dependency manually. `watchEffect(fn)` auto-tracks the dependencies the callback reads, runs once eagerly. |
| **`v-for` without `:key`** | `<li v-for="item in items">` without `:key`. Vue 3 requires `:key` for reordered/keyed reconciliation; without it, DOM elements get reused incorrectly (focus loss, input value carryover). |
| **`:key` as array index on a dynamic list** | `:key="i"` for a list that can be inserted, removed, or reordered. Use a stable per-item identifier. |
| **`v-if` and `v-for` on the same element** | Vue 3 changed precedence: `v-if` now has higher precedence than `v-for`, which is rarely what's intended. Move `v-if` to a wrapping `<template>` or split. |
| **Reading `template ref` before mount** | `const el = ref(); ... el.value.focus()` called in `setup` synchronously — element doesn't exist yet. Read inside `onMounted` or `nextTick`. |
| **`nextTick` to "wait for reactivity"** | `await nextTick()` used to paper over a race that's actually a `computed`/`watch` ordering bug. nextTick is for DOM-after-update timing, not as a "wait for state to settle" mechanism. |
| **`provide`/`inject` for everything** | A component tree where ancestors `provide` dozens of values that descendants `inject`. The dependency graph becomes invisible; refactoring breaks consumers silently. Use Pinia for cross-component state; reserve `provide`/`inject` for genuinely tree-scoped contracts (theme, current user). |
| **Mixing Options API and Composition API in one component** | A component with `data() { ... }` and a separate `<script setup>` block, or `setup()` plus `methods:`. Pick one per component. |
| **Macros called conditionally or imported** | `if (cond) defineProps(...)` or `import { defineProps } from 'vue'`. Macros are compiler hooks, not runtime functions — they must be top-level in `<script setup>` and are auto-imported. |
| **`<script setup>` async without `<Suspense>`** | Top-level `await` inside `<script setup>` requires a `<Suspense>` boundary in an ancestor. Without one, the component renders nothing until the await resolves, with no fallback. |
| **Custom two-way binding via `value` + `@input`** | Component implementing `<MyInput :value="x" @input="x = $event" />` manually instead of using `defineModel()` (3.4+) or `:modelValue` + `@update:modelValue`. |
| **`v-html` on user content** | `v-html="userContent"` — XSS. Use text interpolation `{{ }}` or sanitize explicitly (DOMPurify) before binding. |
| **Watching a deeply-nested object with `deep: true` unconditionally** | `watch(largeObj, ..., { deep: true })` over a complex tree. Every nested mutation triggers the watcher. Either watch specific properties or restructure state. |
| **Teleport target missing or rendered later** | `<Teleport to="#modal-root">` where `#modal-root` doesn't exist at mount, or is rendered by another Vue component that mounts later. The teleport silently fails. |
| **Async component without `<Suspense>` fallback** | `defineAsyncComponent` used in a tree without a `<Suspense>` boundary — flashes empty during load. |
| **Component name resolution mismatch** | Component registered as `MyButton` but referenced as `<my-button>` in a context where the compiler doesn't normalize (some build setups). Standardize on PascalCase in `<script setup>` imports + PascalCase or kebab-case consistently in templates. |
| **`watchEffect` with async callback** | `watchEffect(async () => { ... await ... ... })` — Vue only tracks dependencies read *before* the first await. Reads after the await are not tracked. Either restructure or use `watch` with explicit dependencies. |

---

### Dimension 40: Modern Vue Idioms (`<script setup>`, Composables, Pinia, VueUse)
*Anthony Fu*

| Hazard | What to look for |
|--------|-----------------|
| **`defineComponent({ setup() })` for new components** | Verbose form when `<script setup>` would do the same thing in half the code with better TS inference. Reserve `defineComponent` for components that need runtime options the setup macro doesn't expose. |
| **Options API for new code** | `data()`, `methods:`, `computed:` blocks in new components. Composition API + `<script setup>` is the recommended default; existing Options API code can stay, but new code shouldn't start there. |
| **Vuex in new code** | New stores written in Vuex 4 instead of Pinia. Vuex still works but Pinia is the team's recommendation — better TS, no mutations layer, code-splittable. |
| **Pinia store mutated outside actions** | Component code reaching into a Pinia store's state and mutating it directly (`store.list.push(x)`). State changes belong in store actions; direct mutation works but loses the auditability that's the point of having a store. |
| **Custom reactivity reinventing VueUse** | A locally-written `useLocalStorage`, `useDebounce`, `useEventListener`, `useFetch`, `useIntersectionObserver`. VueUse versions handle SSR, cleanup, and the edge cases the local one usually doesn't. |
| **Composable without cleanup** | A composable that adds an event listener, starts a timer, opens a connection — without `onScopeDispose` (or `onUnmounted` if explicitly component-scoped). Each use leaks the resource. |
| **Composable called outside setup context** | A composable that uses `inject`, registers lifecycle hooks, or relies on the current component instance, called from module top-level or inside a non-setup function. Hooks fail silently; injections return undefined. |
| **Composable returning plain values, not refs** | `function useCounter() { let count = 0; return { count } }` — `count` is a number, not a ref. Caller can't react to it. Composables that expose reactive values return refs / computeds. |
| **`defineProps` without types or with redundant runtime types** | `defineProps({ name: String })` when TypeScript types would do (`defineProps<{ name: string }>()`). Or both — runtime types and TS types listing the same fields, drift inevitable. Pick one (TS preferred for new code; runtime if validation at the boundary matters). |
| **Emitting via literal strings** | `emit('save', value)` without `defineEmits(['save'])` or `defineEmits<{ save: [value: T] }>()`. Listed emits get type checking and template-time validation. |
| **Two-way binding without `defineModel`** | Component with manual `:modelValue` + `@update:modelValue` plumbing for what `defineModel()` (Vue 3.4+) handles in one line. |
| **`withDefaults` chain in 3.5+ code** | `withDefaults(defineProps<...>(), { ... })` where reactive props destructure (`const { foo = 1 } = defineProps<...>()`) is now supported. The compiler preserves reactivity through the destructure. |
| **`shallowRef` opportunity** | A `ref` holding a large array, Map, or class instance whose internals don't need deep tracking — `shallowRef` skips the proxy overhead. Premature optimization for small values; meaningful for large ones. |
| **`watchEffect` cleanup absent** | A `watchEffect` that starts a timer or fetches with cancellation expected — the callback receives `onCleanup` as its first argument; using it is the cancellation path on re-run and unmount. |
| **Pinia state as plain object** | `state: () => ({ count: 0 })` in setup-store form using `reactive` implicitly. The setup-store convention is `const count = ref(0); return { count }` — refs for state, computeds for getters, functions for actions. Matches `<script setup>` conventions. |
| **Composable inferring component lifecycle from "we always call it in setup"** | A composable that registers `onMounted` directly, then someone calls it from an event handler. The lifecycle registration fails silently. Document the contract (must be called from setup) or detect via `getCurrentInstance()` and bail loudly. |
| **Manual `effectScope` without cleanup** | Code creating an `effectScope()` and storing reactive state inside without ever calling `.stop()`. The scope outlives anything that depended on it; effects leak. |
| **SSR-incompatible code in shared composables** | A composable reading `window`, `document`, or `localStorage` at module top-level or inside `setup`, used in an app that renders on the server. SSR crashes or hydration mismatches. Guard with `import.meta.client` (Nuxt) or feature detection. |
| **Nuxt auto-imports obscuring origins** | Heavy reliance on Nuxt auto-imports (`useFetch`, `useState`, `useRouter`) where the import origin matters for the reader. Auto-imports are convenient; jumping into someone else's code and not knowing whether `useState` is Vue's, Nuxt's, or Pinia's is the cost. Flag where the ambiguity bites; live with it where it doesn't. |
| **`defineExpose` exposing internals** | A component using `defineExpose({ ... })` to publish internal refs to parents that then mutate them. Re-introduces tight coupling; usually a sign the API should be a prop + emit instead. |

Evan You's design question: for every reactive value in this component, can you trace what makes it reactive — `ref`, `reactive`, `computed`, `defineProps` — and where reactivity could be lost (destructuring, reassignment, plain-object replacement)? If reactivity behavior surprises you, the destructure or reassignment is usually where.

Anthony Fu's design questions: for every composable, what cleans up its side effects when the calling scope is destroyed? For every Pinia store, are state/getters/actions following the setup-store conventions, and are mutations going through actions? If the codebase is `<script setup>` + Pinia + VueUse, those answers should be quick; if they aren't, the migration is half-done.

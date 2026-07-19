## Svelte Panel

*Activation is governed by the trigger table in `context/panels/triggers.md`. TypeScript-level concerns defer to TypeScript/JS; generic UI concerns defer to UI; this panel covers Svelte-specific machinery — the compiler-first model, runes (Svelte 5), stores, and the SvelteKit boundary between server and client load functions and form actions.*

- **Rich Harris** — Svelte creator; SvelteKit lead; the canonical voice on Svelte's compiler-first philosophy, the runes design (Svelte 5), and the SvelteKit architecture for SSR, load functions, and form actions

Svelte is a single-panelist panel by design. The framework's deliberately compressed surface area — most of the runtime is the compiler, most "framework" code is what other frameworks do at runtime — produces a hazard set narrower than React or Vue. Where production Svelte bugs cluster, they cluster around the Svelte 4→5 migration (`$:` → runes, `export let` → `$props()`, `on:click` → `onclick`, stores → `$state`) and around the SvelteKit server/client boundary.

**Rich Harris's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The compiler is the framework** | Svelte's "runtime" is mostly the compiler output. Components compile to imperative DOM operations — no virtual DOM, no reconciliation. Implication: the source language (template + script) is what the compiler can analyze. Code that fights the compiler's assumptions (mutating non-state values, dynamic property access on `$state`, missing `$bindable()` on a `bind:`-target) won't react. |
| **Runes are reactivity made explicit** | Svelte 5's runes (`$state`, `$derived`, `$effect`, `$props`, `$bindable`, `$inspect`) replace the implicit `let` + `$:` model. `let count = 0` is no longer reactive; `let count = $state(0)` is. This is intentional: implicit reactivity in Svelte 3/4 produced "why isn't this updating" bugs that runes make impossible by construction — the compiler now knows what's reactive. |
| **`$derived` is for derivation; `$effect` is for side effects** | Same discipline as React's `useMemo` / `useEffect` or Vue's `computed` / `watch`. `$derived(...)` produces a value the compiler tracks; `$effect(...)` runs code in response to changes. Code that calls `setState`-equivalent from `$derived` is a bug; code that derives a value inside `$effect` and stores it elsewhere is `$derived` written awkwardly. |
| **Components don't have a setup function** | A component's `<script>` runs *once per instance*. There's no setup/render split — the script is the lifecycle. State declared with `$state()` persists across re-renders because re-rendering is a compile-time concept the runtime doesn't have. This is why hooks-style rules don't apply. |
| **Stores are for cross-component state; component state is the default** | `writable()` / `readable()` / `derived()` stores existed before runes and remain useful for genuinely cross-component state. But "reach for a store" used to be the answer to "I have any state at all" — with runes, component-scoped `$state` covers most needs. New code uses component state until cross-component sharing forces a store (or, in Svelte 5, a rune-based store via a module-level `$state`). |
| **SvelteKit's load function is the data boundary** | Data needed by a route comes from `+page.{ts,server.ts}` or `+layout.{ts,server.ts}` `load` functions. The framework wires them to the component, handles SSR, manages invalidation, and avoids the `useEffect`+`fetch` anti-pattern by construction. Code that fetches in `onMount` instead of `load` forfeits SSR, prefetching, and the framework's invalidation model. |
| **Server load vs universal load is a trust boundary** | `+page.server.ts` runs only on the server; can read databases directly, access secrets, return data the client never sees. `+page.ts` runs in both environments; its return value is serialized to the client. Returning secrets or server-only references from a universal load leaks them. The file suffix is the contract. |
| **Form actions are progressive enhancement, not a JSON API** | SvelteKit form actions (`+page.server.ts` `actions: {}`) accept native form submissions, return validation / data via `fail()` and `redirect()`, and work without JavaScript. `use:enhance` upgrades them with client-side handling without losing the no-JS fallback. Reaching for a `fetch`-to-API-route pattern reinvents what form actions already do, worse. |
| **Snippets replace slots in Svelte 5** | Named slots (`<slot name="header">`) and slot props (`let:value`) are deprecated in favor of snippets — first-class template fragments passed as props, called with `{@render snippet(args)}`. New components use snippets; legacy slot APIs still work but the migration is the direction. |

*Synthesis:* Harris evaluates whether the code embraces Svelte's compiler-first model — runes used correctly (state vs. derived vs. effect), the script-runs-once mental model honored, the SvelteKit server/client boundary respected (load functions vs. effects, server-only data not crossing into universal contexts), and modern primitives chosen over legacy ones (`$state` over implicit reactivity, snippets over slots, form actions over fetch-to-API-route, `$props()` over `export let`). Most production Svelte bugs are one of: a non-`$state` value mutated with reactivity expected, a `$effect` doing the work of `$derived`, an `onMount`-fetched payload that should have been a `load` return, or a `+page.server.ts` load leaking server-only data into the client by returning the wrong shape.

---

## Review Dimensions

---

### Dimension 41: Svelte Runes, Components & Reactivity
*Harris*

| Hazard | What to look for |
|--------|-----------------|
| **Non-`$state` value mutated, reactivity expected (Svelte 5)** | `let count = 0; count++` in a Svelte 5 component — the increment runs, the UI doesn't update. `let count = $state(0)`. The Svelte 3/4 implicit-reactivity migration is the most common source of this in 2024–25. |
| **`$:` reactive statement in Svelte 5 code** | `$: doubled = count * 2` in a runes-mode component. Should be `let doubled = $derived(count * 2)`. Mixing the legacy form and runes in one component is not supported — pick one per component. |
| **`export let` in Svelte 5 code** | `export let name: string` in a runes-mode component. Use `let { name } = $props<{ name: string }>()`. |
| **`on:click` (legacy) vs `onclick` (Svelte 5)** | `<button on:click={fn}>` in a Svelte 5 component. The new form is `<button onclick={fn}>`. Both work in transitional code; new code uses the property form. |
| **`$derived` with side effects** | `const total = $derived(() => { someOther = ...; return sum })`. Derivations must be pure. Side effects belong in `$effect`. |
| **`$effect` for derivation** | `$effect(() => { computed = source * 2 })` storing a derived value in another `$state`. Use `$derived(source * 2)` — the compiler tracks it automatically, no extra state slot needed. |
| **`$effect` without cleanup** | An `$effect` that subscribes, opens a connection, or starts a timer must return a cleanup function: `$effect(() => { const id = setInterval(...); return () => clearInterval(id) })`. Without the return, the resource leaks on component destruction or `$effect` re-run. |
| **Destructuring `$state` object loses fine-grained tracking** | `const state = $state({ a: 1, b: 2 }); const { a } = state` — `a` is a snapshot, not a reactive read. Read through the source (`state.a`) or use individual `$state` slots per property. |
| **`bind:` on a non-`$bindable` prop** | `<Child bind:value={x} />` where the child's `value` prop was declared with `let { value } = $props()` instead of `let { value = $bindable() } = $props()`. The compiler errors in Svelte 5; legacy mode warns. |
| **Store subscription via manual `.subscribe()` outside template** | `myStore.subscribe(v => ...)` in a `<script>` block without cleanup. Inside templates, `$myStore` auto-subscribes / unsubscribes; outside, the manual subscription leaks. Use `$derived` from a rune-based store, or store the returned unsubscribe and call it in cleanup. |
| **Store reached for what `$state` would do** | `import { writable } from 'svelte/store'; const count = writable(0)` for state used by a single component. Component-scoped `$state(0)` is simpler, faster, and doesn't pollute imports. Stores are for cross-component state. |
| **Mutable store exported across modules** | A `writable()` exported and mutated by any importer. Treat the store's `.update`/`.set` as the published API; if exposed broadly, the codebase has no notion of who can change state. |
| **`onMount` for data fetching** | `onMount(async () => { data = await fetch(...) })` in a SvelteKit route. Use `+page.ts` / `+page.server.ts` `load` — SSR works, invalidation works, the loading state can be expressed declaratively. |
| **Direct `document` / `window` access** | `document.querySelector(...)` or `window.X` reads where `bind:this`, actions (`use:`), or a `$effect` reading `globalThis` (with SSR guard) would do. Direct DOM access breaks SSR and skips the compiler's lifecycle handling. |
| **`bind:this` written during render** | `let el = $state(); ... el.focus()` synchronously in the script block — element doesn't exist until after mount. Read inside `$effect(() => { if (el) el.focus() })`. |
| **Untyped `$props()` in TypeScript code** | `let props = $props()` with no type annotation in a `lang="ts"` script. Use `let { foo, bar } = $props<{ foo: string; bar?: number }>()`. |
| **Slot APIs (`<slot>`, `let:`) in Svelte 5 code** | Named slots and slot props in runes-mode components — migrate to snippets (`{@render header()}`, snippet props). The legacy slot syntax still compiles but the team is moving. |
| **`{@html user_content}`** | XSS. Same family as `v-html` (Vue) and `dangerouslySetInnerHTML` (React). Sanitize before binding (DOMPurify) or use text interpolation. |
| **Action without `destroy` / `update` for stateful actions** | `use:myAction` whose returned object is missing `destroy` when the action holds resources, or missing `update` when the action takes parameters that can change. Resources leak; parameter changes are ignored. |
| **Transitions on long lists without `local` flag** | `<li transition:fade>` on every item of a long list. Parent unmount triggers transition on every child simultaneously — janky. Use `transition:fade|local` to scope the transition to local mounts/unmounts. |

---

### Dimension 42: SvelteKit Patterns (Routing, Load, Form Actions)
*Harris*

| Hazard | What to look for |
|--------|-----------------|
| **Data fetched in component, not in `load`** | `onMount` or top-level fetch in a route's `+page.svelte` instead of a `load` function in `+page.{ts,server.ts}`. Forfeits SSR, framework prefetching, and `invalidate()` / `invalidateAll()`. |
| **Universal `+page.ts` load returning server-only data** | A universal load returning database connections, secrets, server-side handles, or non-serializable values. The result is serialized to the client; the server-only reference becomes garbage there, or worse, the secret travels. Use `+page.server.ts` for anything that must not leave the server. |
| **`+page.server.ts` load returning entire DB rows** | Server load returning a full user record including password hashes, tokens, internal flags. Whatever is returned is serialized to the client and visible in network inspector. Project the explicit fields the client needs. |
| **Form submission via `fetch` to an API route** | A form that builds JSON via JS and POSTs to `+server.ts`, reinventing what `+page.server.ts` `actions` already do. Form actions handle the no-JS path (progressive enhancement), validation via `fail()`, redirects via `redirect()`. |
| **Form action without `use:enhance`** | Form action that works fine without JS but the enhanced version is missing — no client-side optimistic updates, no in-page error handling, full navigation on every submit. `use:enhance` from `$app/forms` is the upgrade. |
| **`use:enhance` without handling the result** | `use:enhance` with no callback — the form submits but the page doesn't update with validation errors or success state. Provide a callback that calls `update()` or handles `result.type`. |
| **Throwing plain errors from `load`** | `throw new Error('Not found')` in a load function instead of `throw error(404, 'Not found')` from `@sveltejs/kit`. The framework's `error()` produces a properly-rendered error page; plain throws become 500s. |
| **`goto()` from `load`** | `goto('/login')` called inside a load function. Use `throw redirect(302, '/login')`. `goto` is for client-side navigation after mount; load runs in both SSR and client contexts and needs the framework's redirect handling. |
| **`+layout.server.ts` load doing per-page work** | Expensive per-user work in a layout load that runs on every navigation, when the page-specific load would be more targeted. Layout loads should be for genuinely cross-page concerns; route loads for the route's data. |
| **Missing `invalidate` after mutation** | A form action or mutation that updates server state, then the UI continues showing the cached pre-mutation load result. Either return the new data from the action (so `use:enhance` updates), or call `invalidate(...)` / `invalidateAll()` to trigger re-load. |
| **Sensitive secrets in `+page.ts`** | `import { SECRET } from '$env/static/private'` inside `+page.ts` (universal). Private env vars are server-only; the import fails at build time, but the symptom appears in the form of import errors that suggest "move the import" — the correct move is the whole file becomes `+page.server.ts`. |
| **Hooks (`hooks.server.ts`) doing per-request expensive work without cache** | `handle` hook hitting the database on every request to check auth, with no per-request cache (`event.locals`), causing every nested load and action to re-query. |
| **Route-level state that should be per-load** | Component-scoped `$state` holding data that ought to come from `load` — refreshes on every navigation lose it, and the SSR pass doesn't have it. If the data is route-derived, return it from `load`; if it's user-driven UI state, component state is right. |
| **`+server.ts` returning HTML when a form action would** | Custom JSON endpoints implementing form submission flows. Form actions are the canonical form-handling primitive; `+server.ts` is for genuinely external APIs (webhooks, third-party integrations, public REST endpoints). |
| **`event.locals` populated by hooks but typed as `any`** | `event.locals.user = ...` in `hooks.server.ts` with no corresponding type in `app.d.ts`'s `App.Locals`. Consumers downstream get untyped access; refactors break silently. |
| **Page data accessed via store when `$props()` exists** | `import { page } from '$app/stores'; $page.data` reading load output, when the component receives it via `let { data } = $props()`. The store form was the Svelte 4 pattern; props are the runes-mode equivalent and cleaner. |

Harris's design questions: for every piece of reactive state in this component, is it a `$state`, a `$derived`, or coming through `$props()`? If it's a plain `let`, reactivity stops at the assignment. For every fetch in this codebase, is it in a `load` function or in a component? If in a component, what does the SSR pass render, and what does the user see before hydration? For every form, does it work with JavaScript disabled — and if not, is that a deliberate choice or a missed `use:enhance`?

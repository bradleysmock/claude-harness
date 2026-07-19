## UI Panel

*Activation is governed by the trigger table in `context/panels/triggers.md`. Design-system-specific rules (e.g., USWDS) live in their own panel and activate additively; this panel covers progressive enhancement, accessibility, Tailwind / utility-CSS discipline, and atomic-design thinking as general lenses.*

- **Jeremy Keith** — *Resilient Web Design*, *HTML5 for Web Designers*; progressive enhancement, HTML-first architecture
- **Heydon Pickering** — *Inclusive Design Patterns*, *Inclusive Components*; accessibility, ARIA, inclusive UI
- **Adam Wathan** — creator of Tailwind CSS; utility-first CSS discipline, component extraction thresholds
- **Brad Frost** — *Atomic Design*; design systems, component composition, design token usage

**Jeremy Keith's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **HTML is the foundation** | The page must be meaningful before CSS loads and functional before JS runs. Enhanced elements should have sensible fallback behavior without their enhancement layer (a form still submits, a link still navigates). Progressive enhancement means each layer adds capability without being a prerequisite. |
| **Behavior belongs in declarative markup, not imperative JavaScript** | Interaction declarations belong in HTML attributes or framework-equivalent declarative syntax (HTMX `hx-*`, Hotwire `data-turbo-*`, Alpine `x-*`, framework directives). JavaScript that imperatively wires up behavior the declarative layer already supports is layered wrong. |
| **URLs are the identity of resources** | Every meaningful application state should have a URL. State reachable only by interaction (not by URL or navigation) is a resilience failure — it can't be linked, bookmarked, shared, or navigated back to. |
| **Don't break the back button** | Page fragments and SPA-style transitions that update content without updating the URL silently break browser navigation expectations. Use `history.pushState` / `hx-push-url` / framework-equivalent mechanisms to keep URLs in sync with displayed state. |

**Heydon Pickering's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **ARIA is a repair tool, not a feature** | ARIA roles, properties, and states exist to repair semantic gaps in HTML — not to add meaning to `<div>` soup. The first question is always: is there a semantic HTML element that already does this? If yes, use it. |
| **Interactive elements must be keyboard reachable** | Every element a user can click must also be reachable and activatable via keyboard. `<div>` or `<span>` elements wired with click handlers are not focusable by default — use `<button>` or `<a>` instead. |
| **Live regions for dynamic content** | Content that updates without a page reload (partial swaps, SSE updates, client-side renders) must be announced to screen readers via `aria-live` or the matching role (`role="status"` for transient status messages, `role="log"` for append-only logs, `role="alert"` for important interruptions). |
| **Focus management after dynamic updates** | When content is replaced dynamically, keyboard focus may land in an empty or irrelevant place. For significant content changes (route transition, modal open, step advance), focus should be moved explicitly to the new content's heading or the first interactive element. |
| **Color is not the only indicator** | Status, error states, and active states communicated only by color fail WCAG SC 1.4.1 (Use of Color). Always pair color with an additional indicator (icon, label, pattern, border). |

**Adam Wathan's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Utilities express intent; components encode decisions** | A long class list on a `<div>` is not a problem — it is the design. A component abstraction is only warranted when the same combination of utilities appears in multiple places with identical meaning. Extract when you're duplicating a decision, not when you're duplicating markup. |
| **`@apply` is a last resort** | `@apply` compiles Tailwind utilities into CSS classes, losing the specificity and composition benefits of utilities. It exists for integrating with third-party CSS (e.g., a vendored design-system stylesheet). Using it for in-project markup is usually a sign that a component-level abstraction (a partial, macro, or framework component) is the right fix instead. |
| **Arbitrary values signal missing tokens** | `w-[337px]` is a sign that a design token should exist. Add it to `tailwind.config.js` and give it a meaningful name. Arbitrary values that appear once are usually fine; arbitrary values that appear in multiple places are a missing token. |
| **Responsive variants are explicit** | `md:flex-row`, `lg:hidden` — these are immediately readable. Implicit responsiveness hidden inside CSS classes is not. Tailwind's utility-first approach makes responsive behavior explicit at the markup level; preserve that property. |
| **Keep the config as the source of truth** | All custom colors, spacing, fonts, and breakpoints live in `tailwind.config.js`. Values that appear in CSS files or `style=` attributes are configuration leaking out of its container. |

**Brad Frost's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Atoms compose into molecules compose into organisms** | A button is an atom. A form with a label, input, and button is a molecule. A step panel is an organism. When building custom components, identify which level they are and ensure they only reach down to atoms — never skip levels (an organism that constructs its own atoms inline is duplicating the system). |
| **Design tokens are the design system's API** | Color, spacing, typography, and breakpoint tokens (in the design system's source, in `tailwind.config.js`, or in CSS custom properties) are the contract between design and engineering. A raw hex value, pixel size, or font-family string that isn't a token breaks the contract — future design changes won't propagate. |
| **Components should be agnostic about context** | A well-designed component doesn't know where it lives in the page. Flag components that adjust their appearance based on their parent (margin overrides, color overrides, size variants triggered by container queries on the parent) — these tight couplings prevent reuse. |
| **The pattern library exists; use it** | A project's design system (USWDS, Material, Carbon, Polaris, an in-house library) ships canonical components carrying accessibility, styling, and behavior. Reimplementing one of those components — especially the interactive ones (modal, accordion, combobox, date picker) — is a design-system violation, not a shortcut. |

*Synthesis across UI panelists:* Keith establishes the HTML/behavioral foundation; Pickering evaluates whether it's accessible; Wathan evaluates whether the CSS is disciplined; Frost evaluates whether the component boundaries respect the design system. A finding that fails all four — a `<div>` with an `onclick` that renders a hand-rolled clone of an existing design-system component — is a BLOCKER.

---

## Review Dimensions

---

### Dimension 14: Frontend Architecture
*Keith, Pickering, Wathan, Frost*

| Lens | What to look for |
|------|-----------------|
| **Keith — progressive enhancement** | Does the page remain meaningful and functional without JS? Are interactive elements using semantic HTML (`<button>`, `<a>`, `<form>`) rather than `<div>` + `onclick`? Do meaningful application states have URLs (so they can be linked, bookmarked, navigated back to)? |
| **Keith — behavioral layering** | Interaction declarations belong in declarative markup (HTML attributes, framework directives) where the platform or framework supports it. JavaScript that imperatively reimplements behavior the declarative layer already provides is layered wrong. |
| **Pickering — ARIA correctness** | Are `role`, `aria-*` attributes used to repair semantic gaps, not to add meaning to `<div>` soup? First question is always: is there a semantic HTML element that does this already? |
| **Pickering — keyboard accessibility** | Every interactive element reachable and activatable via keyboard. Non-button elements wired with click handlers but lacking `tabindex`, visible focus, and key handlers for Enter/Space. |
| **Pickering — live regions** | Dynamically-updated content (any swap, fetch, or client-side render of new content) without `aria-live`, `role="status"`, or `role="log"`. Screen readers won't announce the update. |
| **Pickering — focus management** | After a significant content change (route transition, modal open, dynamic swap, step advance), is focus moved explicitly to the new content's heading or first interactive element? |
| **Pickering — color alone** | Status or error states communicated only by color without a secondary indicator (icon, label, border, text). Fails WCAG SC 1.4.1. |
| **Wathan — extract threshold** | Repeated identical utility combinations appearing in 3+ places with the same meaning → extract to a component / macro / partial. One-off utility combinations are correct utility-first usage; the smell is duplicated *decisions*, not duplicated markup. |
| **Wathan — arbitrary values** | `w-[337px]`, `text-[13px]` appearing multiple times → missing design token in `tailwind.config.js`. One-off arbitrary values are usually fine. |
| **Wathan — `@apply` overuse** | `@apply` in project CSS where it isn't bridging to a third-party stylesheet → the fix is a component / macro / partial, not a CSS class. |
| **Frost — design system integrity** | Custom components that duplicate atoms, molecules, or organisms the project's design system already ships. Components that adjust themselves based on parent context (tight coupling). |
| **Frost — token discipline** | Raw hex values, pixel sizes, or font-family strings that aren't design-system tokens or `tailwind.config.js` entries. |

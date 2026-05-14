## UI Panel

*Active when `app/templates/**` or `app/static/**` files are in scope.*

- **Jeremy Keith** — *Resilient Web Design*, *HTML5 for Web Designers*; progressive enhancement, HTML-first architecture
- **Heydon Pickering** — *Inclusive Design Patterns*, *Inclusive Components*; accessibility, ARIA, inclusive UI
- **Adam Wathan** — creator of Tailwind CSS; utility-first CSS discipline, component extraction thresholds
- **Brad Frost** — *Atomic Design*; design systems, component composition, design token usage

**Jeremy Keith's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **HTML is the foundation** | The page must be meaningful before CSS loads and functional before JS runs. HTMX-enhanced elements should have sensible behavior without HTMX (a form still submits, a link still navigates). Progressive enhancement means each layer adds capability without being a prerequisite. |
| **Behavior belongs in HTML attributes, not JavaScript** | HTMX's `hx-get`, `hx-post`, `hx-target` are the right place for interaction declarations. JavaScript that imperatively sets up HTMX-equivalent behavior is the wrong layer. Alpine.js is the right escape hatch for client-side state that has no server equivalent — not for reimplementing server interaction. |
| **URLs are the identity of resources** | Every meaningful application state should have a URL. HTMX's `hx-push-url` is used exactly for this. A state that can only be reached by interaction (not by URL) is a resilience failure. |
| **Don't break the back button** | `hx-push-url` + `hx-history-elt` are the HTMX mechanism for preserving browser history. Page fragments that update without updating the URL silently break navigation expectations. |

**Heydon Pickering's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **ARIA is a repair tool, not a feature** | ARIA roles, properties, and states exist to repair semantic gaps in HTML — not to add meaning to `<div>` soup. The first question is always: is there a semantic HTML element that already does this? If yes, use it. |
| **Interactive elements must be keyboard reachable** | Every element a user can click must also be reachable and activatable via keyboard. HTMX-enhanced `<div>` or `<span>` elements are not focusable by default — use `<button>` or `<a>` instead. |
| **Live regions for dynamic content** | Content that updates without a page reload (HTMX swaps, SSE updates) must be announced to screen readers via `aria-live` or `role="status"`. The chat log uses `role="log"` + `aria-live="polite"` — this is correct; flag deviations. |
| **Focus management after dynamic updates** | When content is replaced by an HTMX swap, keyboard focus may land in an empty or irrelevant place. For significant content changes, focus should be moved explicitly to the new content's heading or the first interactive element. |
| **Color is not the only indicator** | Status, error states, and active states communicated only by color fail WCAG SC 1.4.1 (Use of Color). Always pair color with an additional indicator (icon, label, pattern, border). |

**Adam Wathan's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Utilities express intent; components encode decisions** | A long class list on a `<div>` is not a problem — it is the design. A component abstraction is only warranted when the same combination of utilities appears in multiple places with identical meaning. Extract when you're duplicating a decision, not when you're duplicating markup. |
| **`@apply` is a last resort** | `@apply` compiles Tailwind utilities into CSS classes, losing the specificity and composition benefits of utilities. It exists for integrating with third-party CSS (like USWDS). Using it for in-project markup is usually a sign that a component-level abstraction (a Jinja macro or partial) is the right fix instead. |
| **Arbitrary values signal missing tokens** | `w-[337px]` is a sign that a design token should exist. Add it to `tailwind.config.js` and give it a meaningful name. Arbitrary values that appear once are usually fine; arbitrary values that appear in multiple places are a missing token. |
| **Responsive variants are explicit** | `md:flex-row`, `lg:hidden` — these are immediately readable. Implicit responsiveness hidden inside CSS classes is not. Tailwind's utility-first approach makes responsive behavior explicit at the markup level; preserve that property. |
| **Keep the config as the source of truth** | All custom colors, spacing, fonts, and breakpoints live in `tailwind.config.js`. Values that appear in CSS files or `style=` attributes are configuration leaking out of its container. |

**Brad Frost's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Atoms compose into molecules compose into organisms** | A USWDS `usa-button` is an atom. A form with a label, input, and button is a molecule. A step panel is an organism. When building custom components, identify which level they are and ensure they only reach down to atoms — never skip levels. |
| **Design tokens are the design system's API** | USWDS tokens (mapped into Tailwind via `tailwind.config.js`) are the contract between design and engineering. Using a raw hex value or pixel size that isn't a token breaks this contract — future design changes won't propagate. |
| **Components should be agnostic about context** | A well-designed component doesn't know where it lives in the page. Flag components that adjust their appearance based on their parent (margin adjustments, color overrides) — these tight couplings prevent reuse. |
| **The pattern library exists; use it** | USWDS ships canonical components (`usa-alert`, `usa-summary-box`, `usa-card`, `usa-tag`, `usa-accordion`, `usa-modal`) that carry accessibility, styling, and behavior. Building a Tailwind-styled clone of any of these is a design system violation, not a shortcut. |

*Synthesis across UI panelists:* Keith establishes the HTML/behavioral foundation; Pickering evaluates whether it's accessible; Wathan evaluates whether the CSS is disciplined; Frost evaluates whether the component boundaries respect the design system. A finding that fails all four — a `<div>` with an `onclick` that renders a Tailwind-cloned alert — is a BLOCKER.

---

## Review Dimensions

---

### Dimension 13: UI Consistency (USWDS + Tailwind)
*UI panel. Read `.claude/docs/ui-style-guide.md` before producing findings.*

| Hazard | What to look for |
|--------|-----------------|
| **Tailwind on USWDS components** | A `usa-*` element carrying Tailwind utility classes directly. Layout belongs on a wrapper `<div>`. |
| **USWDS utility classes** | `margin-y-*`, `padding-*`, `display-flex`, `flex-align-*`, `font-sans-*`, `text-bold`, `radius-*` on our markup. Replace with Tailwind equivalents. |
| **Inline styles** | `style="..."` attributes. Extend `tailwind.config.js` instead. |
| **Tailwind clones of USWDS components** | Custom markup that reproduces `usa-alert`, `usa-tag`, `usa-card`, `usa-summary-box`, `usa-modal`, etc. Use the canonical component. |
| **Missing HTMX bridge re-init** | A USWDS component delivered via HTMX swap that DOM-transforms (combo-box, file-input, date-picker) without a branch in `app/static/js/htmx-uswds-bridge.js`. |

Run `.claude/hooks/analyze/ui-consistency.sh` and cite its output line-by-line as findings. Severity: mixing-system patterns are MAJOR by default; a Tailwind clone of a USWDS interactive component is BLOCKER.

---

### Dimension 14: Frontend Architecture
*Keith, Pickering, Wathan, Frost*

| Lens | What to look for |
|------|-----------------|
| **Keith — progressive enhancement** | Does the page remain meaningful and functional without JS? Are HTMX-enhanced elements using semantic HTML (`<button>`, `<a>`, `<form>`) rather than `<div>` + `onclick`? Do meaningful states have URLs (`hx-push-url`)? |
| **Keith — behavioral layering** | Is Alpine.js used only for client-side state with no server equivalent? Is HTMX used for all server interactions? JavaScript that reimplements HTMX behavior in the wrong layer. |
| **Pickering — ARIA correctness** | Are `role`, `aria-*` attributes used to repair semantic gaps, not to add meaning to `<div>` soup? Is the first question always "is there a semantic HTML element that does this"? |
| **Pickering — keyboard accessibility** | Every interactive element reachable and activatable via keyboard. HTMX-enhanced non-button elements that lack `tabindex` and `onkeypress`. |
| **Pickering — live regions** | HTMX swap targets that update dynamically without `aria-live` or `role="log"/"status"`. Screen readers won't announce the update. |
| **Pickering — focus management** | After a significant HTMX swap (e.g., step transition, chat message), is focus managed explicitly to the new content? |
| **Pickering — color alone** | Status or error states communicated only by color without a secondary indicator (icon, label, border). |
| **Wathan — extract threshold** | Repeated identical utility combinations appearing in 3+ places with the same meaning → extract to a Jinja macro or partial. One-off utility combinations are correct Tailwind usage. |
| **Wathan — arbitrary values** | `w-[337px]`, `text-[13px]` appearing multiple times → missing design token in `tailwind.config.js`. |
| **Wathan — `@apply` overuse** | `@apply` in project CSS for non-third-party integration → the fix is a Jinja macro, not a CSS class. |
| **Frost — design system integrity** | Custom components that duplicate existing USWDS atoms, molecules, or organisms. Components that adjust themselves based on parent context (tight coupling). |
| **Frost — token discipline** | Raw hex values or pixel sizes not from `tailwind.config.js` design tokens. |

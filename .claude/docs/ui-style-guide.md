# UI Style Guide — USWDS + Tailwind

This is the **single source of truth** for combining USWDS components with Tailwind utilities in this project. Read it before writing any HTML in `app/templates/**` or class strings in `app/static/js/**`.

The companion stack docs live in `doc/TECH-SPECS.md` (architecture decision) and `tailwind.config.js` (the actual token mapping).

---

## The four rules

### Rule 1 — USWDS owns components

Any element rendered as a canonical USWDS component uses **only** the canonical `.usa-*` class set on that element. No Tailwind utilities for color, spacing, sizing, typography, or layout on the same element. If a component needs visual variation, use the USWDS modifier classes (`--unstyled`, `--secondary`, `--big`, `--outline`) or wrap it in a container that carries the Tailwind layout.

**Exception — wrapper/base classes.** A small set of USWDS classes are deliberately designed to compose with utility layers and are exempt from Rule 1:

- **`usa-prose`** — a typography container that styles its descendants. Routinely combined with Tailwind layout/spacing utilities on the same element.
- **`usa-icon`** — a 1em × 1em sizing base intended to be sized by the consumer. In this project we size it via Tailwind utilities (`w-4 h-4`, `w-5 h-5`, etc.) rather than the `usa-icon--size-*` modifiers.
- **`usa-tag`** — small label. USWDS ships only the `--big` modifier and no status variants (info/warning/error/success); we theme tags via Tailwind `bg-*` / `text-*` tokens.
- **`usa-link`** — anchor base. Hover and focus states are composed via Tailwind `hover:*` / `focus:*` utilities.

When an element carries one of these *alongside* another `usa-*` class (e.g., `usa-button usa-prose`), Rule 1 still applies — it's a component first, wrapper second.

**Exception — transient state utilities.** Tailwind state-prefixed utilities (`hover:*`, `focus:*`, `active:*`, `group-hover:*`) are exempt from Rule 1 on USWDS components. USWDS does not ship parallel state variants for color or opacity, so these fill a real gap and do not conflict with the component's static appearance. For example, `<button class="usa-button usa-button--unstyled text-black hover:text-primary">` is the canonical project pattern for icon-style buttons.

```html
<!-- ✅ Good: USWDS component, canonical classes only -->
<button class="usa-button usa-button--unstyled" type="button">
  Open project
</button>

<!-- ❌ Bad: Tailwind utilities mixed onto a USWDS component -->
<button class="usa-button usa-button--unstyled text-primary px-2 h-7" type="button">
  Open project
</button>

<!-- ✅ Good: layout on a wrapper, component classes stay clean -->
<div class="flex items-center gap-2">
  <button class="usa-button usa-button--unstyled" type="button">Open</button>
  <button class="usa-button usa-button--unstyled" type="button">Close</button>
</div>
```

### Rule 2 — Tailwind owns everything else

Layout, spacing, color, typography, and interactivity on **our own markup** (divs, sections, custom cards, chat bubbles, tables we built ourselves) use **Tailwind utilities only**, with the USWDS tokens already mapped in `tailwind.config.js`. The tokens you'd reach for from USWDS — `primary`, `primary-lighter`, `base-lighter`, `secondary`, `success`, `warning`, `error`, `info`, the `blue-*` and `yellow-*` scales — are all available as Tailwind utilities (`bg-primary`, `text-primary`, `border-base-lighter`).

```html
<!-- ✅ Good: pure Tailwind on our own markup, USWDS tokens via theme -->
<div class="flex flex-col gap-4 rounded border border-base-lighter bg-white p-4">
  <h2 class="text-lg font-semibold text-base-darkest">Section</h2>
  <p class="text-sm text-base-dark">Description</p>
</div>
```

### Rule 3 — Do not use USWDS utility classes

USWDS ships its own utility-class system (`margin-y-8`, `padding-4`, `width-tablet-lg`, `text-primary` as a USWDS class, `bg-base-lighter` as a USWDS class, `display-flex`, `flex-align-center`, etc.). They overlap with Tailwind utilities and are the primary cause of the inconsistency the designer flagged. **Use Tailwind utilities instead** — they read identically once you know the token names are shared.

| ❌ USWDS utility | ✅ Tailwind equivalent |
|---|---|
| `margin-y-8` | `my-8` |
| `padding-4` | `p-4` |
| `padding-x-2` | `px-2` |
| `width-tablet-lg` | `max-w-tablet-lg` (or a Tailwind container utility) |
| `display-flex flex-align-center` | `flex items-center` |
| `font-sans-md` | `text-base` (or the explicit Tailwind size) |
| `text-bold` | `font-semibold` / `font-bold` |
| `radius-md` | `rounded` |

If you find a USWDS utility with no clean Tailwind equivalent, extend the Tailwind theme in `tailwind.config.js` rather than reaching back into USWDS utilities.

### Rule 4 — No inline styles, no custom recreations of USWDS components

- **No `style="..."` attributes** in templates. If a value can't be expressed in tokens, extend `tailwind.config.js`.
- **No Tailwind clones of USWDS components.** Don't build a styled `<div>` that reproduces what `usa-alert`, `usa-summary-box`, `usa-tag`, `usa-card`, `usa-modal`, or `usa-accordion` already provides. Use the canonical component. The bridge in `app/static/js/htmx-uswds-bridge.js` exists specifically so USWDS components keep working after HTMX swaps — building Tailwind clones bypasses both the canonical visual language and the accessibility behavior.

---

## Decision tree

For every element you write, ask:

1. **Is this a USWDS component?** (button, input, alert, modal, tag, accordion, banner, card, summary-box, file-input, combo-box, date-picker, step-indicator, table, breadcrumb, pagination, search, sidenav, header, footer, …)
   - **Yes** → Use only `.usa-*` classes on this element. Layout it with a Tailwind wrapper if needed (Rule 1).
   - **No** → Continue to step 2.

2. **Is this our own markup?** (a layout div, a chat bubble, a custom card, a flex row, a grid)
   - **Yes** → Use Tailwind utilities only, with USWDS tokens via the theme (Rule 2). Never reach for USWDS utility classes (Rule 3).

If you catch yourself wanting an element that is "almost a USWDS component but with one thing different," the answer is almost always to use the USWDS component and adjust through its modifier classes or a wrapper — not to recreate it (Rule 4).

---

## Token reference

USWDS color and design tokens are mapped into Tailwind in `tailwind.config.js` (lines 19–147 for colors). When you want a USWDS color, use the Tailwind utility:

- `bg-primary`, `bg-primary-light`, `bg-primary-lighter`, `bg-primary-dark`, `bg-primary-darker`
- `text-base`, `text-base-dark`, `text-base-darker`, `text-base-darkest`, `text-base-light`, `text-base-lighter`, `text-base-lightest`
- `border-base-light`, `border-base-lighter`, `border-base-lightest`
- `bg-success`, `bg-warning`, `bg-error`, `bg-info` (and their `-light` / `-lighter` / `-dark` variants)
- The full `blue-*` and `yellow-*` USWDS scales (5, 10, 20, 30, 40, 50, 60, 70, 80, 90)

Border radius matches USWDS (`rounded`, `rounded-lg`). Box shadows match USWDS (`shadow-1`, `shadow-2`, `shadow-3`). Typography uses Public Sans Web and Roboto Mono (already configured).

If you need a token that isn't mapped yet, add it to `tailwind.config.js` — don't reach for the raw USWDS utility class.

---

## When components arrive via HTMX

If you add a USWDS component that DOM-transforms its markup (combo-box, file-input, date-picker, time-picker, character-counter) inside an HTMX-swapped fragment, you must add a re-init branch in `app/static/js/htmx-uswds-bridge.js` for that component type. USWDS 3.x binds on `DOMContentLoaded`; HTMX swaps don't fire that. The bridge handles it explicitly per component — there is no public re-init API on the minified bundle.

---

## References

- USWDS components: <https://designsystem.digital.gov/components/>
- USWDS design tokens: <https://designsystem.digital.gov/design-tokens/>
- This project's token mapping: `tailwind.config.js`
- Stack rationale: `doc/TECH-SPECS.md` §1 and §2
- Load order rationale: `app/templates/base.html:7–13`

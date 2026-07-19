## USWDS Design System Panel

*Project-specific. Activation is governed by the trigger table in `context/panels/triggers.md`. Generic UI architecture — progressive enhancement, accessibility, Tailwind discipline, atomic design — lives in `ui.md`; this panel covers the boundary rules specific to running USWDS alongside Tailwind and HTMX.*

- **Brad Frost** — *Atomic Design*; design systems, the cost of off-system components

This is a single-lens panel: Frost's design-system thinking applied to the specific stack (USWDS + Tailwind + HTMX). USWDS itself ships canonical components carrying accessibility, styling, and behavior — the panel's job is to flag every place those guarantees are silently broken by mixing-systems, off-system clones, or missed re-initialization across the HTMX boundary.

**Frost's positions, as applied to USWDS:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The pattern library exists; use it** | USWDS ships canonical components (`usa-alert`, `usa-summary-box`, `usa-card`, `usa-tag`, `usa-accordion`, `usa-modal`, `usa-button`, `usa-table`, `usa-form-group`). Building a Tailwind-styled clone of any of these is a design-system violation, not a shortcut — it forfeits the accessibility audit, theming, and behavior that ship with the canonical component. |
| **Design tokens are the design-system API** | USWDS tokens (color, spacing, typography, breakpoint) are mapped into `tailwind.config.js`. Raw hex values, pixel sizes, or font-stack strings that aren't tokens break the contract — future design changes won't propagate. |
| **Boundary discipline: who owns what** | USWDS owns the component (markup, semantics, behavior). Tailwind owns layout, spacing between components, and one-off page-level styling. Mixing — Tailwind utilities directly on USWDS markup, or USWDS utility classes on non-USWDS markup — is the failure mode. |
| **Components are context-agnostic** | A USWDS component should not adjust itself based on its parent (margin overrides, color overrides). If a USWDS component looks wrong in a layout, the fix is the layout wrapper, not the component. |

Frost's design question: if you removed USWDS from the project tomorrow, which markup would survive intact as portable components, and which is glue-coded to USWDS internals it shouldn't know about?

---

## Review Dimensions

---

### Dimension 13: USWDS + Tailwind + HTMX Bridge Discipline
*Frost lens, project-specific rules.*

Read `.claude/docs/ui-style-guide.md` (if present) before producing findings. Run `.claude/hooks/analyze/ui-consistency.sh` and cite its output line-by-line as findings.

| Hazard | What to look for |
|--------|-----------------|
| **Tailwind utilities on USWDS components** | A `usa-*` element carrying Tailwind utility classes directly (`<button class="usa-button px-6 mt-4">`). Layout/spacing belongs on a wrapper `<div>`. |
| **USWDS utility classes on non-USWDS markup** | `margin-y-*`, `padding-*`, `display-flex`, `flex-align-*`, `font-sans-*`, `text-bold`, `radius-*`, `grid-col-*` outside `usa-*` components. Replace with Tailwind equivalents. |
| **Inline styles** | `style="..."` attributes anywhere. Extend `tailwind.config.js` (for design-system values) or use utility classes (for layout) instead. |
| **Tailwind clone of a canonical USWDS component** | Custom markup that reproduces `usa-alert`, `usa-tag`, `usa-card`, `usa-summary-box`, `usa-modal`, `usa-accordion`, `usa-button`, `usa-table`, `usa-form-group`, etc. Use the canonical component. |
| **Raw color / spacing / font values** | Hex codes, `px` values, or font-family strings that aren't USWDS tokens or Tailwind config entries. Indicates a missing design-token mapping. |
| **Missing HTMX bridge re-init** | A USWDS component delivered via HTMX swap that DOM-transforms on init (combo-box, file-input, date-picker, character-count, tooltip) without a branch in `app/static/js/htmx-uswds-bridge.js`. Swapped-in component arrives as raw markup; behavior never attaches. |
| **USWDS component nested inside a Tailwind-clone container** | A canonical `usa-button` placed inside a hand-rolled "card" `<div>` that imitates `usa-card`. The whole container should be the canonical component. |
| **Theming via component override rather than token** | `.usa-button { background: #1a4480; }` in a project stylesheet instead of setting `$theme-color-primary` in `_uswds-theme.scss`. Breaks every other component that depends on the token. |
| **JS hand-binding for USWDS-provided behavior** | Project JS manually wiring click handlers, focus traps, or aria-state toggles for a USWDS component that ships those behaviors via `@uswds/uswds/js`. Duplicate logic that drifts from upstream. |

**Severity defaults:** Mixing-system patterns (Tailwind utilities on USWDS components, USWDS utilities outside USWDS components) are **MAJOR**. A Tailwind clone of an interactive USWDS component (modal, accordion, combo-box, date-picker) is a **BLOCKER** — it ships an inferior accessibility story under a familiar look.

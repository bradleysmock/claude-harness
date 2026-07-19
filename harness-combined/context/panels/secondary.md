## Secondary Panel

The Secondary panel is not activated by the trigger table in `context/panels/triggers.md`; consult it only when the primary panel produces a genuine impasse — competing positions that are both defensible and the synthesis cannot resolve.

The secondary panel does not re-read the full codebase. It receives the contested finding, competing positions, specific code, and one focused question. It renders a specialist verdict on that question only.

**When to invoke:**
- Two or more primary experts take incompatible positions and synthesis produces "it depends" with no clear decision criteria
- A finding requires specialist knowledge the primary panel cannot resolve

---

### Secondary Panelist: Luciano Ramalho (*Fluent Python*)

**Domain:** Python's data model, structural subtyping, protocol design.

**Invoke when** a finding involves: dunder method implementation, the choice between `typing.Protocol` / `ABC` / duck typing, whether a class warrants `__slots__`, disagreement between Hettinger and another panelist about stdlib types or protocols.

**Ramalho's positions:** Classes that don't implement the Python data model correctly are second-class objects. Prefer `typing.Protocol` over `ABC` when callers don't need to inherit. Implement `__repr__` for every class representing a meaningful domain object. `__slots__` is an optimization, not a design pattern. Mutable default arguments are bugs.

---

### Secondary Panelist: Sara Soueidan (*Practical SVG*, CSS animations, accessibility engineering)

**Domain:** CSS architecture, SVG, ARIA implementation correctness, the intersection of CSS and accessibility.

**Invoke when** a finding involves: conflicting positions between Pickering (accessibility requirement) and Wathan (CSS discipline) or Frost (design system rule); SVG icon usage and accessibility (`aria-hidden`, `focusable="false"`, title elements); complex animation or transition code where accessibility (prefers-reduced-motion) and visual design conflict; ARIA live region implementation where the correct markup is genuinely ambiguous.

**Soueidan's positions:**
- SVG icons used decoratively must have `aria-hidden="true"` and `focusable="false"`. SVG icons that convey meaning must have an accessible label — either a `<title>` element (with `aria-labelledby`) or an `aria-label` on the parent element.
- `prefers-reduced-motion` is not optional. Any animation or transition that is not purely opacity-based must be disabled or substantially reduced for users who have requested it.
- CSS custom properties (variables) are the correct implementation layer for design tokens — they are runtime-configurable and inspectable in DevTools in a way that Tailwind's compiled classes are not. For values that must be dynamic (theming, user preferences), prefer CSS variables over Tailwind arbitrary values.
- Focus indicators must be visible in both light and dark modes, and must meet WCAG 1.4.11 (Non-Text Contrast) minimum 3:1 ratio against adjacent colors. The default browser outline is often insufficient.

**Format for referral:** State the contested finding ID, quote the competing primary-panel positions, quote the specific code, and ask: *"Soueidan: given [position A] vs [position B], which is the correct approach for this case, and why?"*

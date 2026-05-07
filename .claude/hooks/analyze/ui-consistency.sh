#!/usr/bin/env bash
# .claude/hooks/analyze/ui-consistency.sh
# Flags USWDS/Tailwind class-mixing patterns in templates.
# Warning-level: exit 2 = flag (run-all.sh treats this as warning).
# Reference: .claude/docs/ui-style-guide.md

set -uo pipefail

# Skip cleanly when the template directory doesn't exist (non-UI projects).
if [[ ! -d app/templates ]]; then
  echo "UI consistency: no app/templates/ directory — skipping"
  exit 0
fi

python3 << 'PYEOF'
import os
import re
import sys
from pathlib import Path

TEMPLATE_GLOB = "app/templates/**/*.html"

# USWDS utility classes that have a Tailwind equivalent in tailwind.config.js
# (or whose Tailwind equivalent is the canonical idiom). Using these in our
# templates is Rule 3 violation. Anchored at word boundary; trailing -[token]
# captured loosely so margin-y-8, padding-x-2, width-tablet-lg etc. all match.
USWDS_UTILITY_PATTERNS = [
    (r"\bmargin(?:-(?:y|x|top|right|bottom|left))?-(?:neg-)?(?:0|05|1|105|2|205|3|4|5|6|7|8|9|10|15|auto)\b", "USWDS spacing utility — use Tailwind `m-*` / `mx-*` / `my-*` / `mt-*` etc."),
    (r"\bpadding(?:-(?:y|x|top|right|bottom|left))?-(?:0|05|1|105|2|205|3|4|5|6|7|8|9|10|15)\b", "USWDS spacing utility — use Tailwind `p-*` / `px-*` / `py-*` / `pt-*` etc."),
    (r"\bwidth-(?:tablet|mobile|desktop|card|full|auto|fit-content|tablet-lg|mobile-lg|desktop-lg|card-lg)\b", "USWDS width utility — use Tailwind `max-w-*` / `w-*`"),
    (r"\bheight-(?:tablet|mobile|desktop|card|full|auto|viewport|tablet-lg|mobile-lg)\b", "USWDS height utility — use Tailwind `h-*` / `min-h-*` / `max-h-*`"),
    (r"\bdisplay-(?:flex|block|inline-block|inline|none|grid|table|table-cell|list-item|inline-flex|flex-column)\b", "USWDS display utility — use Tailwind `flex` / `block` / `hidden` / `grid` etc."),
    (r"\bflex-(?:align-(?:start|end|center|stretch|baseline)|justify-(?:start|end|center|between|around)|direction-(?:row|column)|no-wrap|column|column-reverse)\b", "USWDS flex utility — use Tailwind `items-*` / `justify-*` / `flex-col`"),
    (r"\bfont-(?:sans|serif|mono|heading|body|alt|code)-(?:3xs|2xs|xs|sm|md|lg|xl|2xl|3xl)\b", "USWDS font sizing — use Tailwind `text-xs` / `text-sm` / `text-base` / `text-lg` / `text-xl`"),
    (r"\bfont-(?:weight|style|family)-[a-z]+\b", "USWDS font utility — use Tailwind `font-*` / `italic` / `not-italic`"),
    (r"\btext-(?:bold|semibold|light|italic|uppercase|lowercase|capitalize|no-underline|underline|tabular)\b", "USWDS text style — use Tailwind `font-bold` / `italic` / `uppercase` / `underline` etc."),
    (r"\bradius-(?:0|sm|md|lg|pill|top-[a-z]+|bottom-[a-z]+|left-[a-z]+|right-[a-z]+)\b", "USWDS radius utility — use Tailwind `rounded` / `rounded-lg` / `rounded-full` etc."),
    (r"\bborder-(?:0|1px|2px|05|105)\b", "USWDS border-width utility — use Tailwind `border` / `border-2` etc."),
    (r"\bsquare-(?:1|2|3|4|5|6|7|8|9|10|15|205|105)\b", "USWDS sizing — use Tailwind `h-* w-*`"),
    (r"\bcircle-(?:1|2|3|4|5|6|7|8|9|10|15|205|105)\b", "USWDS sizing — use Tailwind `rounded-full h-* w-*`"),
    (r"\bgrid-(?:row|col)-?(?:1|2|3|4|5|6|7|8|9|10|11|12|fill|auto)\b", "USWDS grid utility — use Tailwind `grid-cols-*` etc."),
    (r"\bgrid-gap(?:-(?:0|05|1|105|2|205|3|4|5|6))?\b", "USWDS grid-gap — use Tailwind `gap-*`"),
    (r"\bposition-(?:absolute|relative|fixed|static|sticky)\b", "USWDS position utility — use Tailwind `absolute` / `relative` etc."),
    (r"\bz-(?:top|bottom)\b", "USWDS z-index — use Tailwind `z-0` / `z-10` / `z-50` etc."),
]

# Tailwind-shorthand utilities that, if present alongside a `usa-*` component
# class on the same element, indicate Rule 1 violation.
TAILWIND_SHORTHAND = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"-?p[xytrbl]?-\d+(?:\.\d+)?|"
    r"-?m[xytrbl]?-\d+(?:\.\d+)?|"
    r"h-\d+(?:\.\d+)?|h-(?:full|screen|auto|fit)|"
    r"w-\d+(?:\.\d+)?|w-(?:full|screen|auto|fit)|"
    r"min-[hw]-\d+(?:\.\d+)?|min-[hw]-(?:full|screen)|"
    r"max-[hw]-\d+(?:\.\d+)?|max-[hw]-(?:full|screen|prose|none)|"
    r"flex-(?:row|col|wrap|nowrap|1|auto|none|initial)|flex(?![A-Za-z0-9_-])|"
    r"grid-cols-\d+|grid(?![A-Za-z0-9_-])|"
    r"gap-\d+(?:\.\d+)?|gap-[xy]-\d+(?:\.\d+)?|"
    r"items-(?:start|center|end|baseline|stretch)|"
    r"justify-(?:start|center|end|between|around|evenly)|"
    r"text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl)|"
    r"font-(?:thin|light|normal|medium|semibold|bold|black)|"
    r"uppercase|lowercase|capitalize|italic|underline|"
    r"tracking-(?:tighter|tight|normal|wide|wider|widest)|"
    r"leading-\d+|leading-(?:none|tight|snug|normal|relaxed|loose)|"
    r"rounded-(?:sm|md|lg|xl|full|none)|rounded(?![A-Za-z0-9_-])|"
    r"shadow-(?:sm|md|lg|xl|none|1|2|3)|shadow(?![A-Za-z0-9_-])|"
    r"cursor-(?:pointer|default|not-allowed|wait|text|move)|"
    r"transition-(?:colors|all|opacity|transform)|transition(?![A-Za-z0-9_-])|"
    r"(?:hover|focus|active|group-hover):[A-Za-z][A-Za-z0-9_-]*"
    r")(?![A-Za-z0-9_-])"
)

# `usa-*` component classes (the leading element of a USWDS component, not a
# child element). We don't try to enumerate every component; any `usa-` prefix
# is suspect when a Tailwind shorthand is on the same element.
USA_PREFIX = re.compile(r"\busa-[a-z][a-z0-9-]+\b")

# Wrapper/base classes that USWDS designs to compose with utility layers.
# These ship with little-to-no opinionated styling and are explicitly intended
# to be themed by the consumer; mixing Tailwind on them is the canonical
# pattern in this project, not a violation.
#   - `usa-prose`: typography container, styles descendants, freely combines.
#   - `usa-icon`: 1em × 1em base, sized via Tailwind w-*/h-* (USWDS provides
#     `--size-*` modifiers but we use Tailwind for size to stay consistent).
#   - `usa-tag`: small label, USWDS only ships `--big` and provides no status
#     variants (info/warning/error); themed via Tailwind bg-*/text-* tokens.
#   - `usa-link`: anchor base; hover states composed via Tailwind `hover:*`.
WRAPPER_BASE_CLASSES = re.compile(r"\busa-(?:prose|icon|tag|link)(?:--[a-z0-9-]+)?\b")

# Class attributes (HTML and Jinja-style). Conservative — captures the value.
CLASS_ATTR = re.compile(r'class\s*=\s*"([^"]*)"', re.IGNORECASE)

# Inline style attributes.
STYLE_ATTR = re.compile(r'\bstyle\s*=\s*"([^"]+)"', re.IGNORECASE)

findings = []

for path in Path(".").glob(TEMPLATE_GLOB):
    if not path.is_file():
        continue
    try:
        content = path.read_text(errors="ignore")
    except Exception:
        continue

    for line_number, line in enumerate(content.splitlines(), start=1):
        # Inline styles — Rule 4
        if STYLE_ATTR.search(line):
            findings.append((path, line_number, "inline-style", "Inline style=\"...\" — extend tailwind.config.js instead", line.strip()))

        # Class attribute checks
        for class_match in CLASS_ATTR.finditer(line):
            class_value = class_match.group(1)

            # Rule 3 — USWDS utility classes
            for pattern, message in USWDS_UTILITY_PATTERNS:
                hit = re.search(pattern, class_value)
                if hit:
                    findings.append((path, line_number, "uswds-utility", f"`{hit.group(0)}`: {message}", line.strip()))

            # Rule 1 — Tailwind utilities on USWDS component.
            # Skip elements whose ONLY usa-* class is a wrapper/base class
            # (usa-prose / usa-icon / usa-tag / usa-link) — those are designed
            # to compose with utilities. If the element carries any other
            # usa-* class alongside, it's still a component and must remain
            # clean. Transient state utilities (hover:, focus:, active:,
            # group-hover:) are exempt — USWDS does not ship parallel state
            # variants for color/opacity, so these legitimately fill the gap
            # without conflicting with the component's static look.
            usa_classes = USA_PREFIX.findall(class_value)
            if usa_classes:
                non_wrapper = [c for c in usa_classes if not WRAPPER_BASE_CLASSES.fullmatch(c)]
                if non_wrapper:
                    tailwind_hits = [
                        hit for hit in TAILWIND_SHORTHAND.findall(class_value)
                        if hit and not re.match(r'^(?:hover|focus|active|group-hover):', hit)
                    ]
                    if tailwind_hits:
                        seen = sorted(set(tailwind_hits))
                        findings.append((path, line_number, "mixed-component", f"Tailwind utilities on USWDS component element: {', '.join(seen)} — move layout/styling to a wrapper", line.strip()))

if not findings:
    print("UI consistency: clean (no USWDS/Tailwind mixing detected)")
    sys.exit(0)

print(f"UI consistency: {len(findings)} finding(s)")
print()
print("Reference: .claude/docs/ui-style-guide.md")
print()

by_kind = {}
for finding in findings:
    by_kind.setdefault(finding[2], []).append(finding)

for kind in ("mixed-component", "uswds-utility", "inline-style"):
    items = by_kind.get(kind, [])
    if not items:
        continue
    print(f"── {kind} ({len(items)}) ──")
    for path, line_number, _, message, _line in items:
        print(f"  {path}:{line_number} — {message}")
    print()

# Exit 2 = warning/flag (per run-all.sh convention).
sys.exit(2)
PYEOF
SCAN_EXIT=$?

if [[ $SCAN_EXIT -eq 0 ]]; then
  exit 0
fi

if [[ $SCAN_EXIT -eq 2 ]]; then
  echo ""
  echo "Resolution: read .claude/docs/ui-style-guide.md and fix per the four rules."
  echo "  Rule 1 — USWDS components carry only .usa-* classes."
  echo "  Rule 2 — Our own markup uses Tailwind utilities (USWDS tokens via theme)."
  echo "  Rule 3 — Do not use USWDS utility classes; the Tailwind equivalent is the idiom."
  echo "  Rule 4 — No inline styles; extend tailwind.config.js instead."
  exit 2
fi

# Unexpected exit code from the embedded Python — surface as a flag.
echo "UI consistency: scan exited with unexpected status $SCAN_EXIT"
exit 2

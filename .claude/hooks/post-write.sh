#!/usr/bin/env bash
# .claude/hooks/post-write.sh
# Runs fast checks after any file is written.
# Explains every block and failure before exiting.

set -euo pipefail

CHANGED_FILES=$(git diff --name-only 2>/dev/null || echo "")
if [[ -z "$CHANGED_FILES" ]]; then
  exit 0
fi

APP_PY=$(echo "$CHANGED_FILES" | grep -E '^app/.*\.py$' || true)
SERVICE_PY=$(echo "$CHANGED_FILES" | grep -E '^app/services/.*\.py$' || true)
TEST_PY=$(echo "$CHANGED_FILES" | grep -E '^tests/.*\.py$' || true)
HTML_TEMPLATES=$(echo "$CHANGED_FILES" | grep -E '^app/templates/.*\.html$' || true)

# ── Python syntax check ───────────────────────────────────────
ALL_PY=$(printf '%s\n%s\n%s' "$APP_PY" "$TEST_PY" "" | grep '\.py$' || true)
for py_file in $ALL_PY; do
  if [[ -f "$py_file" ]]; then
    if ! python3 -m py_compile "$py_file" 2>/tmp/py-syntax-err.txt; then
      echo ""
      echo "❌  BLOCKED: Syntax error in $py_file"
      echo "    $(head -3 /tmp/py-syntax-err.txt)"
      echo "    Resolution: Fix the syntax error before proceeding."
      exit 1
    fi
  fi
done

# ── Secrets scan ──────────────────────────────────────────────
SECRETS_PATTERN='(password|secret|api_key|apikey|auth_token|bearer)\s*=\s*["\x27][^"\x27]{8,}'
for py_file in $ALL_PY; do
  if [[ -f "$py_file" ]]; then
    if grep -qiP "$SECRETS_PATTERN" "$py_file" 2>/dev/null; then
      echo ""
      echo "🚨  WARNING: Potential credential in $py_file"
      echo "    Pattern matched: hardcoded secret assignment"
      echo "    Resolution: Use environment variables or settings injection."
    fi
  fi
done

# ── JavaScript syntax check ───────────────────────────────────
JS_FILES=$(echo "$CHANGED_FILES" | grep -E '^app/static/.*\.(js)$' || true)
for js_file in $JS_FILES; do
  if [[ -f "$js_file" ]]; then
    if ! node --check "$js_file" 2>/tmp/js-syntax-err.txt; then
      echo ""
      echo "❌  BLOCKED: Syntax error in $js_file"
      echo "    $(head -3 /tmp/js-syntax-err.txt)"
      echo "    Resolution: Fix the syntax error before proceeding."
      exit 1
    fi
  fi
done

# ── UI consistency (HTML templates) ──────────────────────────
if [[ -n "$HTML_TEMPLATES" ]]; then
  if [[ -f ".claude/hooks/analyze/ui-consistency.sh" ]]; then
    echo "▶  UI consistency check..."
    if ! bash .claude/hooks/analyze/ui-consistency.sh 2>&1; then
      echo ""
      echo "❌  BLOCKED: UI consistency violations in templates."
      echo "    Rules: USWDS components use only usa-* classes (no Tailwind on them directly);"
      echo "           everything else uses Tailwind; no USWDS utility classes; no inline styles."
      echo "    Reference: .claude/docs/ui-style-guide.md"
      exit 1
    fi
  fi
fi

# ── Tests (Python app/ or tests/ changes) ────────────────────
if [[ -n "$APP_PY" || -n "$TEST_PY" ]]; then
  if command -v uv &>/dev/null; then
    echo "▶  Running tests..."
    if ! uv run pytest -x -q --ignore=tests/e2e 2>&1; then
      echo ""
      echo "❌  BLOCKED: Tests failed after writing $CHANGED_FILES"
      echo "    Resolution: Fix the failing test before proceeding."
      echo "    (E2E tests are excluded — run 'uv run pytest -m e2e' separately.)"
      exit 1
    fi
  fi
fi

# ── mypy (service layer changes) ─────────────────────────────
if [[ -n "$SERVICE_PY" ]]; then
  if command -v uv &>/dev/null; then
    echo "▶  Type-checking app/services/..."
    if ! uv run mypy app/services/ --no-error-summary 2>&1; then
      echo ""
      echo "❌  BLOCKED: mypy errors in app/services/"
      echo "    Resolution: Fix type errors before proceeding."
      exit 1
    fi
  fi
fi

exit 0

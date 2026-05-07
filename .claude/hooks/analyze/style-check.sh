#!/usr/bin/env bash
# .claude/hooks/analyze/style-check.sh
# Runs code style and formatting checks. Auto-fixes safe issues.
# Exit 0 = pass, 1 = block (unfixable style errors)

set -euo pipefail
LANG="${1:-auto}"
ERRORS=0

check_python() {
  if command -v ruff &>/dev/null; then
    echo "Running ruff (auto-fix)..."
    ruff check --fix src/ tests/ 2>&1 || true
    ruff format src/ tests/ 2>&1 || true
    # Re-check after fixes
    if ! ruff check src/ tests/ 2>&1; then
      echo "Ruff: unfixable style errors remain"
      ERRORS=$((ERRORS + 1))
    fi
  elif command -v flake8 &>/dev/null; then
    flake8 src/ tests/ --max-line-length=99 2>&1 || ERRORS=$((ERRORS + 1))
  else
    echo "No Python linter found (ruff or flake8). Install: pip install ruff"
    # Don't block if no linter installed — just warn
  fi
}

check_typescript() {
  if command -v eslint &>/dev/null; then
    eslint --fix src/ tests/ 2>&1 || ERRORS=$((ERRORS + 1))
  fi
  if command -v prettier &>/dev/null; then
    prettier --write "src/**/*.{ts,js}" "tests/**/*.{ts,js}" 2>&1 || true
  fi
}

case "$LANG" in
  python) check_python ;;
  typescript|javascript) check_typescript ;;
  *) check_python 2>/dev/null; check_typescript 2>/dev/null ;;
esac

if [[ $ERRORS -gt 0 ]]; then
  echo "Style errors remain after auto-fix. Manual correction required."
  exit 1
fi
echo "Style: clean"
exit 0

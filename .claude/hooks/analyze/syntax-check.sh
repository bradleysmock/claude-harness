#!/usr/bin/env bash
# .claude/hooks/analyze/syntax-check.sh
# Validates syntax for all source and test files.
# Exit 0 = pass, 1 = block (syntax errors found)

set -euo pipefail
LANG="${1:-auto}"
ERRORS=0

check_python() {
  while IFS= read -r -d '' f; do
    if ! python3 -m py_compile "$f" 2>/tmp/syn-err.txt; then
      echo "SYNTAX ERROR: $f"
      cat /tmp/syn-err.txt
      ERRORS=$((ERRORS + 1))
    fi
  done < <(find src tests -name "node_modules" -prune -o -name "*.py" -print0 2>/dev/null)
}

check_typescript() {
  if command -v tsc &>/dev/null && [[ -f tsconfig.json ]]; then
    tsc --noEmit 2>&1 || { ERRORS=$((ERRORS + 1)); return; }
  fi
  # Fallback: node --check only works for plain JS, not TS
  while IFS= read -r -d '' f; do
    if ! node --check "$f" 2>/tmp/syn-err.txt; then
      echo "SYNTAX ERROR: $f"
      cat /tmp/syn-err.txt
      ERRORS=$((ERRORS + 1))
    fi
  done < <(find src tests -name "node_modules" -prune -o -name "*.js" -print0 2>/dev/null)
}

check_go() {
  if command -v go &>/dev/null; then
    go build ./... 2>&1 || ERRORS=$((ERRORS + 1))
  fi
}

case "$LANG" in
  python)    check_python ;;
  typescript|javascript) check_typescript ;;
  go)        check_go ;;
  *)
    check_python 2>/dev/null || true
    check_typescript 2>/dev/null || true
    ;;
esac

if [[ $ERRORS -gt 0 ]]; then
  echo "$ERRORS syntax error(s) found. Fix all syntax errors before proceeding."
  exit 1
fi
echo "Syntax: clean"
exit 0

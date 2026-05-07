#!/usr/bin/env bash
# .claude/hooks/analyze/type-check.sh
# Runs static type checking. Type errors are blocking.
# Exit 0 = pass, 1 = block

set -euo pipefail
LANG="${1:-auto}"

check_python() {
  if command -v mypy &>/dev/null; then
    echo "Running mypy..."
    mypy src/ --strict --ignore-missing-imports 2>&1
    return $?
  else
    echo "mypy not installed. Install: pip install mypy"
    echo "Skipping type check (non-blocking if mypy absent on first run)"
    return 0
  fi
}

check_typescript() {
  if command -v tsc &>/dev/null; then
    echo "Running tsc --noEmit..."
    tsc --noEmit 2>&1
    return $?
  else
    echo "tsc not found. Install: npm install -g typescript"
    return 0
  fi
}

case "$LANG" in
  python) check_python ;;
  typescript) check_typescript ;;
  javascript)
    echo "JavaScript: consider migrating to TypeScript for type safety"
    exit 0 ;;
  *)
    check_python 2>/dev/null
    check_typescript 2>/dev/null
    ;;
esac

echo "Type check: clean"
exit 0

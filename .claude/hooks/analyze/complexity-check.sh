I still #!/usr/bin/env bash
# .claude/hooks/analyze/complexity-check.sh
# Reports cyclomatic complexity. Warning only — never blocks.
# Exit 0 always; findings printed for awareness.

set -euo pipefail
LANG="${1:-auto}"
FLAG_ABOVE="${COMPLEXITY_FLAG_ABOVE:-10}"
BLOCK_ABOVE="${COMPLEXITY_BLOCK_ABOVE:-20}"

check_python_complexity() {
  if ! command -v radon &>/dev/null; then
    pip install radon -q 2>/dev/null || true
  fi
  if ! command -v radon &>/dev/null; then
    echo "radon not available — skipping complexity check"
    return 0
  fi

  local result
  result=$(radon cc src/ -j 2>/dev/null || echo '{}')
  python3 -c "
import json, sys
data = json.loads('''$result'''.replace(\"'\", '\"'))
found = False
for file, items in data.items():
    for item in items:
        cc = item.get('complexity', 0)
        name = item.get('name', '?')
        lineno = item.get('lineno', '?')
        if cc > $BLOCK_ABOVE:
            print(f'NOTE:  {file}:{lineno} {name}() complexity={cc} (>{$BLOCK_ABOVE} — consider decomposing)')
            found = True
        elif cc > $FLAG_ABOVE:
            print(f'NOTE:  {file}:{lineno} {name}() complexity={cc} (>{$FLAG_ABOVE} — may be worth simplifying)')
            found = True
if not found:
    print('Complexity: all functions within threshold')
" 2>/dev/null || echo "Complexity: check skipped (parse error)"
}

check_js_complexity() {
  local deep_nesting
  deep_nesting=$(grep -rn ".\{120,\}" src/ 2>/dev/null | head -5 || true)
  if [[ -n "$deep_nesting" ]]; then
    echo "NOTE: Lines >120 chars may indicate high complexity:"
    echo "$deep_nesting"
  else
    echo "Complexity: no long lines detected"
  fi
}

case "$LANG" in
  python) check_python_complexity ;;
  typescript|javascript) check_js_complexity ;;
  *) check_python_complexity 2>/dev/null || true ;;
esac

# Always exit 0 — this check is advisory only
exit 0

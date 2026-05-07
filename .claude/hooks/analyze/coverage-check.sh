#!/usr/bin/env bash
# .claude/hooks/analyze/coverage-check.sh
# Runs tests under coverage and enforces thresholds.
# Exit 0 = pass, 1 = block (below threshold)

set -euo pipefail
LANG="${1:-auto}"
LINE_THRESHOLD="${COVERAGE_LINE_THRESHOLD:-80}"
BRANCH_THRESHOLD="${COVERAGE_BRANCH_THRESHOLD:-70}"

run_python_coverage() {
  if ! command -v pytest &>/dev/null; then
    pip install pytest pytest-cov -q 2>/dev/null || true
  fi
  if command -v pytest &>/dev/null; then
    echo "Running pytest with coverage..."
    pytest tests/ \
      --cov=src \
      --cov-report=term-missing \
      --cov-report=json:.claude/state/coverage.json \
      --cov-branch \
      -q 2>&1

    python3 << PYEOF
import json, sys
try:
    with open('.claude/state/coverage.json') as f:
        data = json.load(f)
    totals = data.get('totals', {})
    line_pct = totals.get('percent_covered', 0)
    branch_pct = totals.get('percent_covered_display', line_pct)
    # Get branch separately
    branch_covered = totals.get('covered_branches', 0)
    branch_total = totals.get('num_branches', 1)
    branch_pct = (branch_covered / branch_total * 100) if branch_total > 0 else 100

    print(f"Line coverage:   {line_pct:.1f}% (threshold: $LINE_THRESHOLD%)")
    print(f"Branch coverage: {branch_pct:.1f}% (threshold: $BRANCH_THRESHOLD%)")

    failed = False
    if line_pct < $LINE_THRESHOLD:
        print(f"BLOCK: Line coverage {line_pct:.1f}% < {$LINE_THRESHOLD}%")
        failed = True
    if branch_pct < $BRANCH_THRESHOLD:
        print(f"BLOCK: Branch coverage {branch_pct:.1f}% < {$BRANCH_THRESHOLD}%")
        failed = True

    if failed:
        print("\nAdd tests to cover the uncovered lines shown above.")
        sys.exit(1)
    else:
        print("Coverage: thresholds met ✅")
except FileNotFoundError:
    print("Coverage report not generated — check pytest output above")
    sys.exit(1)
PYEOF
  else
    echo "pytest not available — coverage check skipped"
  fi
}

run_node_coverage() {
  if [[ -f package.json ]]; then
    echo "Running test coverage..."
    if command -v npx &>/dev/null; then
      npx jest --coverage --coverageThreshold="{\"global\":{\"lines\":$LINE_THRESHOLD,\"branches\":$BRANCH_THRESHOLD}}" 2>&1 || {
        echo "BLOCK: Coverage below threshold"
        exit 1
      }
    fi
  fi
}

case "$LANG" in
  python) run_python_coverage ;;
  typescript|javascript) run_node_coverage ;;
  *)
    run_python_coverage 2>/dev/null
    run_node_coverage 2>/dev/null
    ;;
esac

EXIT=$?
if [[ $EXIT -ne 0 ]]; then
  echo "Coverage: BLOCK — add tests to meet the threshold"
  exit 1
fi
echo "Coverage: thresholds satisfied"
exit 0

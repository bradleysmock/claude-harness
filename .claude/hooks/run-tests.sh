#!/usr/bin/env bash
# .claude/hooks/run-tests.sh
# Runs the test suite. Used in Stage 3 to verify tests pass after implementation.
# Usage: bash .claude/hooks/run-tests.sh [--expect-fail]

set -euo pipefail
EXPECT_FAIL=false
if [[ "${1:-}" == "--expect-fail" ]]; then
  EXPECT_FAIL=true
fi

# Detect test runner from project
detect_runner() {
  if [[ -f pytest.ini ]] || [[ -f pyproject.toml ]] || find tests -name "*.py" -quit 2>/dev/null; then
    echo "pytest"
  elif [[ -f package.json ]] && grep -q '"jest"' package.json 2>/dev/null; then
    echo "jest"
  elif [[ -f package.json ]] && grep -q '"vitest"' package.json 2>/dev/null; then
    echo "vitest"
  elif find . -name "*_test.go" -quit 2>/dev/null; then
    echo "go-test"
  else
    echo "unknown"
  fi
}

RUNNER=$(detect_runner)
echo "Test runner: $RUNNER"
echo ""

run_pytest() {
  if ! command -v pytest &>/dev/null; then
    pip install pytest -q
  fi
  if [[ "$EXPECT_FAIL" == "true" ]]; then
    # Run tests and expect them all to fail (TDD sub-task 3a verification)
    local output
    output=$(pytest tests/ -v --tb=no -q 2>&1) || true
    local passed
    passed=$(echo "$output" | grep -c "PASSED" || true)
    if [[ "$passed" -gt 0 ]]; then
      echo "⚠️  WARNING: $passed test(s) pass against an empty implementation."
      echo "   These tests are not verifying real behaviour. Rewrite them to fail first."
      echo ""
      echo "Passing tests:"
      echo "$output" | grep "PASSED"
      exit 1
    fi
    echo "✅ All tests fail as expected (correct TDD state)"
    return 0
  else
    pytest tests/ -v --tb=short 2>&1
    return $?
  fi
}

run_jest() {
  npx jest --verbose 2>&1
}

run_vitest() {
  npx vitest run 2>&1
}

run_go() {
  go test ./... -v 2>&1
}

case "$RUNNER" in
  pytest) run_pytest ;;
  jest) run_jest ;;
  vitest) run_vitest ;;
  go-test) run_go ;;
  *)
    echo "Could not detect test runner."
    echo "Ensure your test framework is configured (pytest, jest, vitest, go test)."
    exit 1
    ;;
esac

EXIT=$?
if [[ $EXIT -ne 0 ]]; then
  echo ""
  echo "❌ Tests failed. Fix the implementation (not the tests) unless the test is provably wrong."
  exit 1
fi
echo ""
echo "✅ All tests pass"
exit 0

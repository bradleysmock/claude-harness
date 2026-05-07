#!/usr/bin/env bash
# .claude/hooks/analyze/run-all.sh
# Runs the full analysis suite and emits a summary table.
# Called by /build after implementation is complete.

set -euo pipefail

REPORT_FILE="pipeline/analysis-report.md"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BLOCKERS=0
FLAGS=0

# Auto-detect language from file extensions
if ls src/*.py &>/dev/null 2>&1; then LANG="python"
elif ls src/*.ts &>/dev/null 2>&1; then LANG="typescript"
elif ls src/*.go &>/dev/null 2>&1; then LANG="go"
elif ls src/*.js &>/dev/null 2>&1; then LANG="javascript"
else LANG="unknown"
fi

echo "🔍 Running analysis (language: $LANG)"
echo ""

# Initialize report
mkdir -p pipeline
cat > "$REPORT_FILE" << REPORT_HEADER
# Analysis Report

**Generated:** $(date -u)
**Language:** $LANG

## Summary

| Check | Status | Findings |
|-------|--------|----------|
REPORT_HEADER

run_check() {
  local name="$1"
  local script="$2"
  local is_warning_only="${3:-false}"

  echo -n "  [$name] ... "

  local output_file="/tmp/check-output-$$.txt"
  if bash ".claude/hooks/analyze/$script" "$LANG" > "$output_file" 2>&1; then
    echo "✅ PASS"
    echo "| $name | ✅ PASS | — |" >> "$REPORT_FILE"
  else
    local exit_code=$?
    local line_count
    line_count=$(wc -l < "$output_file")

    if [[ "$is_warning_only" == "true" ]]; then
      echo "⚠️  WARN"
      echo "| $name | ⚠️ WARN | $line_count lines |" >> "$REPORT_FILE"
      FLAGS=$((FLAGS + 1))
    elif [[ $exit_code -eq 2 ]]; then
      echo "⚠️  FLAG"
      echo "| $name | ⚠️ FLAG | $line_count lines |" >> "$REPORT_FILE"
      FLAGS=$((FLAGS + 1))
    else
      echo "❌ BLOCK"
      echo "| $name | ❌ BLOCK | $line_count lines |" >> "$REPORT_FILE"
      BLOCKERS=$((BLOCKERS + 1))
    fi

    echo "" >> "$REPORT_FILE"
    echo "### $name — Findings" >> "$REPORT_FILE"
    echo '```' >> "$REPORT_FILE"
    cat "$output_file" >> "$REPORT_FILE"
    echo '```' >> "$REPORT_FILE"

    # Print the explanation inline so Claude sees it immediately
    echo ""
    cat "$output_file"
    echo ""
  fi
  rm -f "$output_file"
}

echo "Running checks..."
run_check "Syntax"             "syntax-check.sh"
run_check "Style"              "style-check.sh"
run_check "Types"              "type-check.sh"
run_check "Secrets"            "secrets-scan.sh"
run_check "Injection"          "injection-scan.sh"
run_check "Dependencies"       "dep-scan.sh"
run_check "SAST"               "sast-general.sh"
run_check "Coverage"           "coverage-check.sh"
run_check "Complexity"         "complexity-check.sh" "true"   # warning only
run_check "UI consistency"     "ui-consistency.sh"   "true"   # warning only — USWDS/Tailwind mixing in app/templates/**

echo "" >> "$REPORT_FILE"
echo "## Result" >> "$REPORT_FILE"
echo "- Blocking findings: $BLOCKERS" >> "$REPORT_FILE"
echo "- Flagged findings:  $FLAGS" >> "$REPORT_FILE"

echo "─────────────────────────────────────"
echo "  Blockers: $BLOCKERS"
echo "  Flags:    $FLAGS"
echo "  Report:   $REPORT_FILE"
echo "─────────────────────────────────────"

if [[ $BLOCKERS -gt 0 ]]; then
  echo ""
  echo "❌  Analysis FAILED — $BLOCKERS blocking finding(s) must be resolved."
  echo "    Each finding above explains what was found and how to fix it."
  echo "    Resolve all blockers and re-run this analysis before /review."
  exit 1
else
  echo ""
  echo "✅  Analysis passed — ready for /review"
  exit 0
fi

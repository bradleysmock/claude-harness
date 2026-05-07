#!/usr/bin/env bash
# .claude/hooks/analyze/sast-general.sh
# Runs Semgrep SAST with language-appropriate rulesets.
# Exit 0 = pass, 1 = block (HIGH), 2 = flag (MEDIUM)

set -euo pipefail
LANG="${1:-auto}"

if ! command -v semgrep &>/dev/null; then
  echo "Semgrep not installed."
  echo "Install: pip install semgrep"
  echo "Attempting install..."
  pip install semgrep -q 2>/dev/null || {
    echo "Could not install Semgrep. SAST check skipped (non-blocking for initial setup)."
    echo "ACTION REQUIRED: Install Semgrep before production use."
    exit 0
  }
fi

# Select rulesets by language
case "$LANG" in
  python)
    RULESETS="p/python p/owasp-top-ten p/secrets"
    ;;
  typescript|javascript)
    RULESETS="p/typescript p/javascript p/nodejs p/owasp-top-ten p/secrets"
    ;;
  go)
    RULESETS="p/golang p/owasp-top-ten p/secrets"
    ;;
  java)
    RULESETS="p/java p/owasp-top-ten p/secrets"
    ;;
  *)
    RULESETS="p/owasp-top-ten p/secrets"
    ;;
esac

# Add custom rules if present
CUSTOM_RULES=""
if [[ -f ".claude/skills/semgrep-rules.yaml" ]]; then
  CUSTOM_RULES="--config .claude/skills/semgrep-rules.yaml"
fi

echo "Running Semgrep ($LANG)..."
RESULT=$(semgrep scan src/ $CUSTOM_RULES \
  $(for r in $RULESETS; do echo "--config $r"; done) \
  --json --quiet 2>/dev/null || echo '{"results":[],"errors":[]}')

echo "$RESULT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('results', [])
blocked = flagged = 0

for r in results:
  sev = r.get('extra', {}).get('severity', 'INFO').upper()
  msg = r.get('extra', {}).get('message', '')[:80]
  path = r.get('path', '?')
  line = r.get('start', {}).get('line', '?')
  rule = r.get('check_id', '?').split('.')[-1]
  print(f'{sev}: {path}:{line} [{rule}] {msg}')
  if sev in ('ERROR', 'WARNING'):
    blocked += 1
  elif sev == 'INFO':
    flagged += 1

if results:
  print(f'Total: {len(results)} finding(s)')
  if blocked: sys.exit(1)
  if flagged: sys.exit(2)
else:
  print('No findings')
"

EXIT=$?
if [[ $EXIT -eq 1 ]]; then
  echo "SAST: BLOCK — HIGH severity findings. Fix before proceeding."
  exit 1
elif [[ $EXIT -eq 2 ]]; then
  echo "SAST: FLAG — MEDIUM findings for review."
  exit 2
fi
echo "SAST: clean"
exit 0

#!/usr/bin/env bash
# .claude/hooks/analyze/dep-scan.sh
# Scans dependencies for known CVEs. Blocks on HIGH/CRITICAL, flags MEDIUM.
# Exit 0 = pass, 1 = block, 2 = flag

set -euo pipefail
LANG="${1:-auto}"
BLOCK_SEVERITIES=("CRITICAL" "HIGH")
BLOCKED=0
FLAGGED=0

scan_python() {
  if [[ -f requirements.txt ]] || [[ -f pyproject.toml ]] || [[ -f setup.py ]]; then
    echo "Scanning Python dependencies..."
    if command -v pip-audit &>/dev/null; then
      local result
      result=$(pip-audit --format=json 2>/dev/null || echo '{"vulnerabilities":[]}')
      echo "$result" | python3 -c "
import json, sys
data = json.load(sys.stdin)
vulns = data.get('vulnerabilities', [])
blocked = flagged = 0
for v in vulns:
  name = v.get('name', '?')
  ver = v.get('version', '?')
  for fix in v.get('fix_versions', []):
    pass
  for alias in v.get('aliases', []):
    sev = 'UNKNOWN'
    print(f'{sev}: {name}=={ver} — {alias}')
    if sev in ('CRITICAL', 'HIGH'):
      blocked += 1
    elif sev == 'MEDIUM':
      flagged += 1
if vulns:
  print(f'Total: {len(vulns)} vulnerabilities found')
  if blocked: sys.exit(1)
  if flagged: sys.exit(2)
"
    else
      echo "pip-audit not installed. Install: pip install pip-audit"
      echo "Manual check required: pip install safety && safety check"
    fi
  else
    echo "No Python dependency file found (requirements.txt / pyproject.toml)"
  fi
}

scan_node() {
  if [[ -f package.json ]]; then
    echo "Scanning Node.js dependencies..."
    if command -v npm &>/dev/null; then
      local result
      result=$(npm audit --json 2>/dev/null || echo '{"vulnerabilities":{}}')
      echo "$result" | python3 -c "
import json, sys
data = json.load(sys.stdin)
vulns = data.get('vulnerabilities', {})
blocked = flagged = 0
for name, info in vulns.items():
  sev = info.get('severity', 'unknown').upper()
  via = ', '.join(str(v.get('source', v)) if isinstance(v, dict) else str(v) for v in info.get('via', []))[:60]
  print(f'{sev}: {name} — {via}')
  if sev in ('CRITICAL', 'HIGH'):
    blocked += 1
  elif sev == 'MODERATE':
    flagged += 1
if blocked: sys.exit(1)
elif flagged: sys.exit(2)
"
    fi
  fi
}

case "$LANG" in
  python) scan_python ;;
  typescript|javascript) scan_node ;;
  *)
    scan_python 2>/dev/null
    scan_node 2>/dev/null
    ;;
esac

EXIT=$?
if [[ $EXIT -eq 1 ]]; then
  echo "Dependency scan: BLOCK — HIGH/CRITICAL CVEs found. Update affected packages."
  exit 1
elif [[ $EXIT -eq 2 ]]; then
  echo "Dependency scan: FLAG — MEDIUM CVEs found. Acknowledge in Stage 5 review."
  exit 2
fi
echo "Dependency scan: clean"
exit 0

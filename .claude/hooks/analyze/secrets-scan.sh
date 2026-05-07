#!/usr/bin/env bash
# .claude/hooks/analyze/secrets-scan.sh
# Scans for hardcoded secrets. ANY hit is a hard block with immediate escalation.
# Exit 0 = pass, 1 = HARD BLOCK

set -euo pipefail
LANG="${1:-auto}"

FOUND=0

# ── Pattern-based scan (always runs) ─────────────────────────
echo "Scanning for hardcoded secrets..."

python3 << 'PYEOF'
import re, sys, pathlib

PATTERNS = [
    (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{6,}["\']', "Hardcoded password"),
    (r'(?i)(api_key|apikey|api-key)\s*=\s*["\'][^"\']{10,}["\']', "Hardcoded API key"),
    (r'(?i)(secret|secret_key)\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded secret"),
    (r'(?i)(access_token|auth_token)\s*=\s*["\'][^"\']{10,}["\']', "Hardcoded token"),
    (r'(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}', "Hardcoded Bearer token"),
    (r'(?i)(aws_access_key_id|aws_secret)\s*=\s*["\'][^"\']{10,}["\']', "AWS credential"),
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key ID pattern"),
    (r'(?i)-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----', "Private key"),
    (r'(?i)(mongodb|postgres|mysql|redis)://[^@]+:[^@]+@', "Connection string with credentials"),
    (r'(?i)ghp_[A-Za-z0-9]{36}', "GitHub personal access token"),
    (r'(?i)sk-[A-Za-z0-9]{48}', "OpenAI API key pattern"),
    (r'(?i)xox[baprs]-[A-Za-z0-9-]+', "Slack token"),
]

# Allowlist patterns (test files, example values, env var references)
ALLOWLIST = [
    r'os\.environ',
    r'process\.env',
    r'getenv',
    r'your[-_]',
    r'example[-_]',
    r'\$\{',
    r'<your',
    r'placeholder',
    r'test[-_]secret',
    r'fake[-_]',
    r'mock[-_]',
    r'dummy[-_]',
]

found = []
for path in pathlib.Path('.').rglob('*'):
    if not path.is_file():
        continue
    # Skip binary files, .git, node_modules, .venv
    skip_dirs = {'.git', 'node_modules', '.venv', '__pycache__', '.claude/state'}
    if any(skip in path.parts for skip in skip_dirs):
        continue
    if path.suffix in ('.pyc', '.png', '.jpg', '.pdf', '.zip', '.tar', '.gz'):
        continue
    try:
        content = path.read_text(errors='ignore')
    except Exception:
        continue

    for lineno, line in enumerate(content.splitlines(), 1):
        for pattern, desc in PATTERNS:
            if re.search(pattern, line):
                # Check allowlist
                if any(re.search(a, line, re.IGNORECASE) for a in ALLOWLIST):
                    continue
                found.append(f"  {path}:{lineno} — {desc}")
                print(f"🚨 {desc}: {path}:{lineno}")

if found:
    print(f"\n🚨 SECRETS DETECTED: {len(found)} finding(s)")
    print("This is a HARD BLOCK. Remove all secrets immediately.")
    print("Use environment variables or a secrets manager instead.")
    print("\nIf these are false positives, add them to .gitleaksignore")
    sys.exit(1)
else:
    print("No secret patterns detected")
    sys.exit(0)
PYEOF

PATTERN_EXIT=$?

# ── Gitleaks (if available) ───────────────────────────────────
if command -v gitleaks &>/dev/null; then
  echo "Running gitleaks..."
  if ! gitleaks detect --source=. --no-git --quiet 2>&1; then
    echo "🚨 Gitleaks detected secrets — HARD BLOCK"
    FOUND=1
  fi
fi

if [[ $PATTERN_EXIT -ne 0 || $FOUND -ne 0 ]]; then
  echo ""
  echo "🚨 SECRETS SCAN: HARD BLOCK"
  echo "   Action: Remove all hardcoded secrets immediately"
  echo "   Escalation: Notify the security team if secrets may have been committed to git history"
  echo "   Fix: Use environment variables, .env files (gitignored), or a secrets manager"
  exit 1
fi

echo "Secrets scan: clean"
exit 0

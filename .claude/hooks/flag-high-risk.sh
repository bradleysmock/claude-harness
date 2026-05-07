#!/usr/bin/env bash
# .claude/hooks/flag-high-risk.sh
# Scans a design artifact or source file for high-risk security patterns.
# Usage: bash .claude/hooks/flag-high-risk.sh <file>
# Exit 0 = no high-risk patterns, 1 = high-risk patterns found (flag only, not block)

set -euo pipefail
TARGET="${1:-pipeline/design-artifact.md}"
HIGH_RISK_PATTERNS="${HIGH_RISK_PATTERNS:-authentication,authorisation,authorization,payment,cryptography,crypto,jwt,oauth,rbac,session,password,token,privilege,admin,superuser,sudo}"

python3 - "$TARGET" "$HIGH_RISK_PATTERNS" << 'PYEOF'
import sys, re, pathlib

target = sys.argv[1]
patterns = sys.argv[2].split(',')

if not pathlib.Path(target).exists():
    print(f"File not found: {target}")
    sys.exit(0)

content = pathlib.Path(target).read_text(errors='ignore').lower()

found = []
for pattern in patterns:
    p = pattern.strip()
    if re.search(r'\b' + re.escape(p) + r'\b', content):
        found.append(p)

if found:
    print("⚠️  HIGH-RISK PATTERNS DETECTED:")
    for p in found:
        print(f"   • {p}")
    print()
    print("This component requires:")
    print("  1. Human design review before Stage 3")
    print("  2. Named human approver in Stage 5")
    if 'confidential' in content or 'restricted' in content:
        print("  3. Second reviewer (CONFIDENTIAL/RESTRICTED classification)")
    print()
    print("Append a '## Security Review Required' section to the design artifact.")
    sys.exit(1)
else:
    print("No high-risk patterns detected")
    sys.exit(0)
PYEOF

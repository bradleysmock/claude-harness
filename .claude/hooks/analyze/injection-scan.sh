#!/usr/bin/env bash
# .claude/hooks/analyze/injection-scan.sh
# Scans for injection vulnerabilities (SQL, command, path traversal, etc.)
# Exit 0 = pass, 1 = block

set -euo pipefail
LANG="${1:-auto}"

python3 << 'PYEOF'
import re, sys, pathlib

# Injection patterns by category
PATTERNS = {
    "SQL Injection": [
        (r'(?i)(execute|query|cursor\.execute)\s*\(\s*[f"\'].*%s.*\+', "String concatenation in SQL"),
        (r'(?i)f["\'].*SELECT.*\{', "f-string SQL query"),
        (r'(?i)(execute|query)\s*\(\s*["\'].*\+\s*\w+', "String concat SQL"),
        (r'(?i)\"SELECT.*\"\s*\+', "SQL string concat with +"),
        (r'(?i)format\s*\(.*SELECT', "format() in SQL query"),
    ],
    "Command Injection": [
        (r'(?i)(os\.system|subprocess\.call|subprocess\.run)\s*\(\s*\w+\s*\+', "User input in system call"),
        (r'(?i)shell=True.*\+', "shell=True with string concat"),
        (r'(?i)eval\s*\(.*request|eval\s*\(.*input|eval\s*\(.*param', "eval() with user input"),
        (r'(?i)exec\s*\(.*request|exec\s*\(.*input', "exec() with user input"),
    ],
    "Path Traversal": [
        (r'(?i)open\s*\(\s*.*(?:request|input|param)', "File open with user input"),
        (r'(?i)(?:join|path)\s*\(.*(?:request|input|param)\.', "Path join with user-controlled input"),
        (r'(?i)(?:open|readFile|createReadStream)\s*\([^)]*\.\.\/', "File open with ../ traversal sequence"),
    ],
    "XSS": [
        (r'(?i)(render|innerHTML|document\.write)\s*[=(].*request', "Unescaped user input in HTML"),
        (r'(?i)Markup\s*\(\s*\w+\s*\)', "Flask Markup without escape"),
        (r'(?i)\|safe.*request|request.*\|safe', "Jinja2 |safe with request data"),
    ],
    "SSRF": [
        (r'(?i)(requests\.get|urllib\.request|httpx\.get)\s*\(\s*\w+\s*[\+)]', "HTTP request with dynamic URL"),
        (r'(?i)(fetch|axios\.get)\s*\(\s*\w+\s*[\+)]', "Fetch with user-controlled URL"),
    ],
    "Deserialization": [
        (r'(?i)pickle\.loads\s*\(', "pickle.loads — unsafe deserialization"),
        (r'(?i)yaml\.load\s*\([^,]+\)', "yaml.load without Loader — use yaml.safe_load"),
        (r'(?i)marshal\.loads\s*\(', "marshal.loads — unsafe"),
    ],
}

# Allowlist: test files, known safe patterns
ALLOWLIST_PATHS = ['tests/', 'test_', '_test.py', '.claude/']
ALLOWLIST_PATTERNS = [
    r'parameterized|params\s*=\s*\(',
    r'#\s*(nosec|noqa)',
    r'safe_load',
    r'sanitize|sanitise',
    r'escape\(',
    r'''^\s*(import|from|require)\s+['"]''',   # module import statements
    r'''^\s*from\s+['"][./]''',                 # relative imports
    r'''require\(['"][./]''',                   # require() relative imports
]

found = []
EXCLUDED_DIRS = {'node_modules', 'dist', 'coverage', '.angular', 'cache', '__pycache__'}

for path in pathlib.Path('src').rglob('*') if pathlib.Path('src').exists() else []:
    if not path.is_file():
        continue
    if any(part in EXCLUDED_DIRS for part in path.parts):
        continue
    if path.suffix not in ('.py', '.ts', '.js', '.go', '.java', '.rb', '.php'):
        continue
    try:
        content = path.read_text(errors='ignore')
    except Exception:
        continue

    for lineno, line in enumerate(content.splitlines(), 1):
        # Skip allowlisted patterns
        if any(re.search(a, line, re.IGNORECASE) for a in ALLOWLIST_PATTERNS):
            continue
        for category, patterns in PATTERNS.items():
            for pattern, desc in patterns:
                if re.search(pattern, line):
                    finding = f"BLOCK [{category}]: {path}:{lineno} — {desc}"
                    if finding not in found:
                        found.append(finding)
                        print(finding)

if found:
    print(f"\n{len(found)} injection vulnerability candidate(s) found.")
    print("Each must be reviewed and fixed. Use parameterised queries, input validation, and output encoding.")
    sys.exit(1)
else:
    print("No injection patterns detected")
    sys.exit(0)
PYEOF

EXIT=$?
if [[ $EXIT -ne 0 ]]; then
  echo "Injection scan: BLOCK — address all findings above"
  exit 1
fi
echo "Injection scan: clean"
exit 0

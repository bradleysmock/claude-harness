#!/usr/bin/env bash
# .claude/hooks/validate-spec.sh
# Validates a pipeline specification YAML file against all Gate 1 rules.
# Usage: bash .claude/hooks/validate-spec.sh <spec_file>

set -euo pipefail

SPEC_FILE="${1:-pipeline/spec.yaml}"

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "❌ Specification file not found: $SPEC_FILE"
  echo "   Create it using the template: .claude/templates/specification.yaml"
  exit 1
fi

python3 - "$SPEC_FILE" << 'PYEOF'
import sys, re, json
from pathlib import Path

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyyaml', '-q'], check=True)
    import yaml

spec_file = sys.argv[1]
with open(spec_file) as f:
    spec = yaml.safe_load(f)

errors = []
warnings = []
score = 0

AMBIGUOUS_WORDS = [
    'fast', 'slow', 'quick', 'efficient', 'secure', 'appropriate', 'suitable',
    'good', 'bad', 'better', 'best', 'simple', 'easy', 'hard', 'complex',
    'scalable', 'performant', 'reasonable', 'acceptable', 'adequate', 'sufficient',
    'if possible', 'where applicable', 'as needed', 'when necessary',
    'ideally', 'preferably', 'optimally', 'should consider',
]

APPROVED_LANGUAGES = ['python', 'typescript', 'javascript', 'go', 'rust', 'java', 'kotlin', 'ruby', 'php', 'csharp', 'cpp', 'c']
SECURITY_LEVELS = ['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED']
ACTION_VERBS = ['must', 'shall', 'should', 'will', 'can', 'accepts', 'returns', 'validates', 'processes',
                'stores', 'retrieves', 'sends', 'receives', 'creates', 'updates', 'deletes', 'reads',
                'writes', 'logs', 'emits', 'handles', 'rejects', 'allows', 'denies', 'authenticates',
                'authorises', 'authorizes', 'exposes', 'implements', 'provides', 'supports', 'enforces']

print("=" * 60)
print("STAGE 1 — SPECIFICATION VALIDATION REPORT")
print("=" * 60)
print(f"File: {spec_file}\n")

# ── FIELD 1: task_statement ──────────────────────────────────
ts = spec.get('task_statement', '')
print("▶ Field: task_statement")
if not ts:
    errors.append("MISSING: task_statement is required")
elif len(ts) > 280:
    errors.append(f"FAIL: task_statement exceeds 280 characters ({len(ts)} chars)")
else:
    score += 1
    print(f"  ✅ Present ({len(ts)} chars)")

# Ambiguity in task statement
ts_lower = ts.lower()
found_ambiguous = [w for w in AMBIGUOUS_WORDS if w in ts_lower]
if found_ambiguous:
    warnings.append(f"AMBIGUITY in task_statement: unquantified terms: {found_ambiguous}")
    print(f"  ⚠️  Ambiguous terms: {found_ambiguous}")

# ── FIELD 2: functional_requirements ────────────────────────
reqs = spec.get('functional_requirements', [])
print("\n▶ Field: functional_requirements")
if not reqs:
    errors.append("MISSING: functional_requirements is required")
elif len(reqs) < 3:
    errors.append(f"FAIL: minimum 3 functional requirements required (found {len(reqs)})")
else:
    if len(reqs) >= 5:
        score += 2
    else:
        score += 1
    print(f"  ✅ {len(reqs)} requirements found")

for i, req in enumerate(reqs):
    req_str = str(req).strip().lower()
    starts_with_verb = any(req_str.startswith(v) or f' {v} ' in req_str[:30] for v in ACTION_VERBS)
    if not starts_with_verb:
        warnings.append(f"FR-{i+1}: Does not begin with an action verb: '{str(req)[:60]}...'")
    for word in AMBIGUOUS_WORDS:
        if word in req_str:
            warnings.append(f"FR-{i+1}: Ambiguous term '{word}' — quantify this: '{str(req)[:60]}'")

# ── FIELD 3: non_functional_requirements ────────────────────
nfrs = spec.get('non_functional_requirements', [])
print("\n▶ Field: non_functional_requirements")
if not nfrs:
    errors.append("MISSING: at least one non_functional_requirement is required")
else:
    # Check for numeric thresholds
    measurable = [n for n in nfrs if re.search(r'\d+\s*(ms|s|%|mb|gb|rpm|rps|req|concurrent|users)', str(n).lower())]
    if len(measurable) >= len(nfrs):
        score += 2
        print(f"  ✅ {len(nfrs)} NFRs, all measurable")
    elif measurable:
        score += 1
        print(f"  ⚠️  {len(measurable)}/{len(nfrs)} NFRs have measurable thresholds")
        warnings.append(f"NFR: {len(nfrs)-len(measurable)} NFR(s) lack numeric thresholds")
    else:
        errors.append("FAIL: No NFRs have measurable thresholds (e.g., '<100ms', '99.9%', '<50MB')")
        print(f"  ❌ {len(nfrs)} NFRs found but none are measurable")

# ── FIELD 4: target_language ────────────────────────────────
lang_info = spec.get('target_language', {})
print("\n▶ Field: target_language")
if not lang_info:
    errors.append("MISSING: target_language is required")
else:
    lang = str(lang_info.get('language', lang_info) if isinstance(lang_info, dict) else lang_info).lower()
    if lang in APPROVED_LANGUAGES:
        score += 1
        print(f"  ✅ {lang} — in approved stack")
    else:
        errors.append(f"FAIL: '{lang}' is not in the approved language stack: {APPROVED_LANGUAGES}")

# ── FIELD 5: codebase_context ───────────────────────────────
ctx = spec.get('codebase_context', '')
print("\n▶ Field: codebase_context")
if not ctx or str(ctx).strip() in ('', 'null', 'none', 'N/A'):
    warnings.append("codebase_context is empty — generation quality will be lower without context")
    print("  ⚠️  Empty — provide relevant interfaces/schemas for best results")
else:
    score += 1
    print(f"  ✅ Present")

# ── FIELD 6: security_classification ────────────────────────
sec = spec.get('security_classification', '')
print("\n▶ Field: security_classification")
if not sec:
    errors.append("MISSING: security_classification is required (PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED)")
else:
    if str(sec).upper() in SECURITY_LEVELS:
        score += 1
        print(f"  ✅ {sec}")
    else:
        errors.append(f"FAIL: '{sec}' is not a valid security level. Use: {SECURITY_LEVELS}")

# ── FIELD 7: acceptance_criteria ────────────────────────────
criteria = spec.get('acceptance_criteria', [])
print("\n▶ Field: acceptance_criteria")
if not criteria:
    errors.append("MISSING: acceptance_criteria is required")
elif len(criteria) < 2:
    errors.append(f"FAIL: minimum 2 acceptance criteria required (found {len(criteria)})")
else:
    gwt_pattern = re.compile(r'\b(given|when|then|assert|verify|expect|ensure)\b', re.IGNORECASE)
    gwt_count = sum(1 for c in criteria if gwt_pattern.search(str(c)))
    if gwt_count >= len(criteria):
        score += 2
        print(f"  ✅ {len(criteria)} criteria, all in testable form")
    elif gwt_count > 0:
        score += 1
        print(f"  ⚠️  {gwt_count}/{len(criteria)} criteria in Given/When/Then form")
        warnings.append(f"AC: {len(criteria)-gwt_count} criteria lack testable Given/When/Then structure")
    else:
        errors.append("FAIL: No acceptance criteria use testable form (Given/When/Then or assert/verify/expect)")

# ── EDGE CASE COVERAGE ───────────────────────────────────────
all_text = json.dumps(spec).lower()
edge_indicators = ['error', 'invalid', 'empty', 'null', 'none', 'timeout', 'concurrent', 'limit', 'max', 'min', 'overflow', 'not found', '404', 'unauthor', 'forbidden']
has_edge = any(w in all_text for w in edge_indicators)
print("\n▶ Edge case coverage")
if has_edge:
    score += 1
    print("  ✅ Edge/error cases referenced")
else:
    warnings.append("No edge cases or error scenarios mentioned — add at least one to improve generation quality")
    print("  ⚠️  No edge cases found — add error/boundary scenarios")

# ── FINAL REPORT ─────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"SCORE: {score}/10")
print("=" * 60)

if errors:
    print(f"\n❌ BLOCKING ERRORS ({len(errors)}):")
    for e in errors:
        print(f"   • {e}")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"   • {w}")

print()
if errors or score < 8:
    if score < 8 and not errors:
        print(f"🔴 GATE 1: FAIL — Score {score}/10 is below the required threshold of 8/10")
    else:
        print(f"🔴 GATE 1: FAIL — {len(errors)} blocking error(s) must be resolved")
    print("\nAddress all blocking errors and improve the specification, then re-run /intake.")
    sys.exit(1)
else:
    print(f"🟢 GATE 1: PASS — Score {score}/10")
    if warnings:
        print(f"   {len(warnings)} warning(s) noted — review before proceeding")
    print("\nProceed to: /design")
    sys.exit(0)
PYEOF

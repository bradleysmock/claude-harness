#!/usr/bin/env bash
# mutation-diff.sh <path> [base_ref]
# Diff-scoped mutation testing with a new-code ratchet: mutate only code changed
# vs. the merge-base, and gate on the changed code's score. Auto-detects the engine.
# Engine thresholds (Stryker thresholds.break / PIT mutationThreshold) do the gating;
# this wrapper wires up the diff scope.

set -euo pipefail

TARGET="${1:?usage: mutation-diff.sh <path> [base_ref]}"
BASE_REF="${2:-origin/main}"
KILL_TARGET="${KILL_TARGET:-75}"   # percent; keep in sync with engine config

git fetch --no-tags --depth=200 "${BASE_REF%%/*}" "${BASE_REF#*/}" 2>/dev/null || true
CHANGED="$(git diff --name-only --diff-filter=d "${BASE_REF}...HEAD" -- "$TARGET" 2>/dev/null || true)"

if [ -f package.json ]; then
  echo "→ Stryker (JS/TS), diff-scoped since ${BASE_REF}"
  npx stryker run --since="${BASE_REF}" --incremental \
    || { echo "Mutation gate FAILED (kill-rate below thresholds.break=${KILL_TARGET})"; exit 1; }

elif [ -f pom.xml ] || ls build.gradle* >/dev/null 2>&1; then
  echo "→ PIT (JVM), changed files only"
  # Requires pitest-maven + the SCM/git plugin; <mutationThreshold> self-fails the build.
  mvn -q -DwithHistory -Pmutation org.pitest:pitest-maven:scmMutationCoverage \
    || { echo "Mutation gate FAILED (below <mutationThreshold>)"; exit 1; }

elif [ -f pyproject.toml ] || [ -f setup.cfg ]; then
  echo "→ mutmut (Python), changed paths: ${CHANGED:-<none>}"
  [ -z "$CHANGED" ] && { echo "No mutable changes."; exit 0; }
  mutmut run --paths-to-mutate "$(echo "$CHANGED" | paste -sd, -)"
  # mutmut has no native threshold-break; parse and enforce:
  python3 - "$KILL_TARGET" <<'PY'
import subprocess, sys, re
target = float(sys.argv[1])
out = subprocess.run(["mutmut","results"],capture_output=True,text=True).stdout
killed = len(re.findall(r"killed", out)); survived = len(re.findall(r"survived", out))
total = killed + survived
score = 100.0*killed/total if total else 100.0
print(f"mutation score: {score:.1f}% ({killed}/{total})")
sys.exit(0 if score >= target else 1)
PY

else
  echo "No supported build manifest found (package.json / pom.xml / pyproject.toml)." >&2
  exit 3
fi

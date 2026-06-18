#!/usr/bin/env bash
# refactor-probe.sh <path>
# Q4 refactor-robustness probe, Tier 1 (warn-only until its FP rate is zero).
# Applies a PROVABLY behavior-preserving transform — renaming local/private
# identifiers — and re-runs the related tests. A test that was green and is now
# red is implementation-coupled (a change-detector), since renaming a private
# cannot change observable behavior.
#
# The rename codemod is language-specific and is the one piece you implement per
# stack (ts-morph / jscodeshift for TS; a headless IDE refactor for Java). This
# script is the harness around it.

set -euo pipefail
TARGET="${1:?usage: refactor-probe.sh <path>}"
CODEMOD="${RENAME_CODEMOD:-}"   # e.g. node tools/rename-privates.codemod.js

if [ -z "$CODEMOD" ]; then
  echo "WARN: set RENAME_CODEMOD to your Tier-1 private-rename codemod. Skipping (warn-only)." >&2
  exit 0
fi

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
git stash push -q --include-untracked || true
$CODEMOD "$TARGET"

set +e
# adapt the runner to your stack:
npx jest --findRelatedTests "$TARGET" --ci >"$WORK/after.txt" 2>&1
RESULT=$?
set -e

git checkout -- "$TARGET" 2>/dev/null || true
git stash pop -q 2>/dev/null || true

if [ "$RESULT" -ne 0 ]; then
  echo "Q4 WARN: tests failed after a behavior-preserving rename → implementation-coupled:"
  grep -E '✕|FAIL' "$WORK/after.txt" || true
  echo "(warn-only; promote to blocking once FP rate is zero)"
fi
exit 0

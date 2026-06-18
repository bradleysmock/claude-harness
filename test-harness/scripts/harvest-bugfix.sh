#!/usr/bin/env bash
# harvest-bugfix.sh <path>
# Highest-value oracle harvester: closed bug-fix commits (high-independence
# regression oracles) and reverts (negative oracles) touching <path>.
# Prints candidates; the oracle-extract command turns them into ledger claims.
# Resolving linked issue bodies needs a tracker token (GH_TOKEN / GITHUB_TOKEN) —
# this script surfaces the refs; fetch bodies in oracle-extract.

set -euo pipefail
TARGET="${1:?usage: harvest-bugfix.sh <path>}"

echo "## Bug-fix candidates touching ${TARGET}"
git log --follow --date=short \
  --grep='fix\|bug\|regression\|hotfix\|defect' -i \
  --pretty=format:'%h|%ad|%s' -- "$TARGET" | while IFS='|' read -r sha date subj; do
    refs="$(echo "$subj" | grep -oE '#[0-9]+|[A-Z]+-[0-9]+' | paste -sd, - || true)"
    echo "- ${date}  ${sha}  ${subj}   ${refs:+[issue: ${refs}]}"
done

echo
echo "## Reverts touching ${TARGET} (negative oracles)"
git log --grep='revert' -i --pretty=format:'- %ad  %h  %s' --date=short -- "$TARGET" || true

echo
echo "# Next: for each, fetch the linked issue body (expected vs. actual) and the"
echo "# tests added in the fix commit; emit example/regression claims with"
echo "# independence=high, authority=high, locator='issue#<n> + <sha>'."

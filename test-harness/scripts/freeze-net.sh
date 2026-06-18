#!/usr/bin/env bash
# freeze-net.sh <file-or-glob> [<file-or-glob> ...]
# Records the characterization-net files and their checksums into
# .test-harness/frozen-net.txt. After this, net-guard.sh blocks edits to them.

set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
MANIFEST="$ROOT/.test-harness/frozen-net.txt"
mkdir -p "$(dirname "$MANIFEST")"

if [ "$#" -eq 0 ]; then
  echo "usage: freeze-net.sh <test-file-or-glob> [...]" >&2
  exit 1
fi

sha() { command -v sha256sum >/dev/null && sha256sum "$1" | awk '{print $1}' || shasum -a 256 "$1" | awk '{print $1}'; }

{
  echo "# frozen characterization net — generated $(date -u +%FT%TZ)"
  echo "# path<TAB>sha256 — net-guard.sh blocks edits to these files"
  for pat in "$@"; do
    for f in $pat; do
      [ -f "$f" ] || continue
      printf '%s\t%s\n' "$(realpath "$f")" "$(sha "$f")"
    done
  done
} > "$MANIFEST"

echo "Froze $(grep -vc '^#' "$MANIFEST") file(s) → $MANIFEST"
# Optional belt-and-suspenders: make them read-only on disk too.
# grep -v '^#' "$MANIFEST" | cut -f1 | xargs -r chmod a-w

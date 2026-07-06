Generate or refresh the `## [Unreleased]` section of `CHANGELOG.md` from completed tickets and conventional commits since the last git tag.

Run the command from the project root (where `.tickets/` and `CHANGELOG.md` live). It is read-only with respect to tickets and git history — it only writes `CHANGELOG.md` and echoes the generated block to stdout.

## Behavior

- **Boundary**: the most recent git tag reachable from `HEAD` (`git describe --tags --abbrev=0`); if there is no tag, all history is used. If neither a tag nor a root commit can be resolved (e.g. a repository with no commits), the command fails closed with a non-zero exit — it never silently treats "no boundary" as "all history".
- **Tickets**: every `.tickets/completed/*/status.md` whose `updated:` date is after the tag date (or, when `updated:` is absent/malformed, whose directory was modified after the tag's commit time) contributes its `title:`. Ticket type is inferred from the slug prefix (`feat-` / `fix-` / `chore-`), else `other`.
- **Commits**: every subject in `git log <tag>..HEAD` matching the conventional-commit prefix `type(scope): …` is categorized by `type`; non-conventional subjects go to `other`.
- **Sanitizing**: every ticket title and commit subject is stripped of CR/LF and a leading `#`, and has the Markdown structural characters `[ ] ( ) < >` backslash-escaped, **before** it is categorized, deduplicated, or written. This is what prevents a crafted subject such as `[Unreleased] - 2026-01-01` from masquerading as the block heading.
- **Deduplication**: a commit whose subject (after stripping its conventional prefix, lower-casing, and trimming) equals a completed ticket's title (lower-cased, trimmed) is dropped — the ticket entry wins.
- **Output**: a Keep-a-Changelog block `## [Unreleased] - YYYY-MM-DD` with `### feat` / `### fix` / `### chore` / `### other` subsections (empty subsections omitted). It is written atomically to `CHANGELOG.md` — created if absent, the existing `## [Unreleased]` block replaced in place if present (idempotent, with a warning to stderr), otherwise prepended above existing content — and printed to stdout.

The date defaults to today; set `CHANGELOG_DATE=YYYY-MM-DD` to override it (used by the test suite for determinism).

## Command

Run this script verbatim from the project root:

```bash
set -euo pipefail

date_str="${CHANGELOG_DATE:-$(date +%F)}"

# Scratch workspace (tag-ref file, per-category accumulators, atomic-write target).
work=$(mktemp -d) || { echo "changelog: cannot create temp dir" >&2; exit 1; }
trap 'rm -rf "$work"' EXIT
: > "$work/feat"; : > "$work/fix"; : > "$work/chore"; : > "$work/other"
: > "$work/ticket_norms"

# Sanitize an external string: drop CR/LF, drop a leading '#', escape Markdown
# structural chars. Applied before any comparison, categorization, or output.
sanitize() {
    printf '%s' "$1" \
        | tr -d '\r\n' \
        | sed -e 's/^#//' \
              -e 's/\[/\\[/g' -e 's/\]/\\]/g' \
              -e 's/(/\\(/g' -e 's/)/\\)/g' \
              -e 's/</\\</g' -e 's/>/\\>/g'
}

# Lower-case and trim outer whitespace (dedup normalization; no mid-string edits).
normalize() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# --- Boundary detection (fail closed) ---------------------------------------
tag=""
if tag=$(git describe --tags --abbrev=0 2>/dev/null); then
    :
else
    tag=""
    root=$(git rev-list --max-parents=0 HEAD 2>/dev/null | tail -1 || true)
    if [ -z "$root" ]; then
        echo "changelog: cannot determine a boundary (no tag and no commits)" >&2
        exit 1
    fi
fi

# --- Tag reference file + tag date (only when a tag exists) ------------------
tmpref="$work/tagref"
tag_date=""
if [ -n "$tag" ]; then
    tag_epoch=$(git log -1 --format=%at "$tag" 2>/dev/null) \
        || { echo "changelog: cannot read tag commit time" >&2; exit 1; }
    tag_date=$(git log -1 --format=%as "$tag" 2>/dev/null) \
        || { echo "changelog: cannot read tag date" >&2; exit 1; }
    # epoch -> touch -t stamp [[CC]YY]MMDDhhmm.SS, portably: BSD `date -r` first,
    # then the GNU `date -d @` form. The stamp is applied with POSIX `touch -t`
    # (the GNU-only `-d` flag for touch is intentionally never used).
    stamp=$(date -r "$tag_epoch" "+%Y%m%d%H%M.%S" 2>/dev/null) \
        || stamp=$(date -u -d "@$tag_epoch" "+%Y%m%d%H%M.%S" 2>/dev/null) \
        || { echo "changelog: cannot format tag time" >&2; exit 1; }
    touch -t "$stamp" "$tmpref" \
        || { echo "changelog: cannot create tag reference file" >&2; exit 1; }
fi

# --- Ticket collector -------------------------------------------------------
if [ -d .tickets/completed ]; then
    for sf in .tickets/completed/*/status.md; do
        [ -e "$sf" ] || continue
        dir=$(dirname "$sf")
        base=$(basename "$dir")
        slug=${base#*-}
        # Extract the first title:/updated: field. Avoid `sed | head -1`: under
        # `set -e -o pipefail`, head closing the pipe early can SIGPIPE sed on a
        # multi-line match and abort the whole command. Capture then take line 1.
        title=$(sed -n 's/^title:[[:space:]]*//p' "$sf"); title=${title%%$'\n'*}
        [ -n "$title" ] || continue
        updated=$(sed -n 's/^updated:[[:space:]]*//p' "$sf"); updated=${updated%%$'\n'*}

        include=0
        if [ -z "$tag" ]; then
            include=1
        elif printf '%s' "$updated" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
            if [[ "$updated" > "$tag_date" ]]; then include=1; fi
        else
            # Fallback path: mtime vs the tag reference file. A missing ref file
            # must be fatal here, never silently inclusive.
            if [ ! -f "$tmpref" ]; then
                echo "changelog: tag reference file missing; cannot filter by mtime" >&2
                exit 1
            fi
            if [ -n "$(find "$dir" -newer "$tmpref" 2>/dev/null)" ]; then include=1; fi
        fi
        [ "$include" -eq 1 ] || continue

        case "$slug" in
            feat-*)  cat=feat ;;
            fix-*)   cat=fix ;;
            chore-*) cat=chore ;;
            *)       cat=other ;;
        esac
        stitle=$(sanitize "$title")
        printf -- '- %s\n' "$stitle" >> "$work/$cat"
        normalize "$stitle" >> "$work/ticket_norms"
        printf '\n' >> "$work/ticket_norms"
    done
fi

# --- Commit collector -------------------------------------------------------
if [ -n "$tag" ]; then
    range="$tag..HEAD"
else
    range="HEAD"
fi
while IFS= read -r subj; do
    [ -n "$subj" ] || continue
    ssubj=$(sanitize "$subj")
    # Categorize on the sanitized subject. Because the sanitizer escapes '(' and
    # ')', the conventional scope appears as \(...\) — match it in escaped form.
    if printf '%s' "$ssubj" | grep -Eq '^(feat|fix|chore)(\\\([^:]*\\\))?:'; then
        cat=$(printf '%s' "$ssubj" | sed -E 's/^(feat|fix|chore).*/\1/')
    else
        cat=other
    fi
    # Dedup key: strip the (escaped) conventional prefix, then normalize.
    stripped=$(printf '%s' "$ssubj" | sed -E 's/^[a-z]+(\\\([^:]*\\\))?:[[:space:]]*//')
    norm=$(normalize "$stripped")
    if [ -n "$norm" ] && grep -Fxq -e "$norm" "$work/ticket_norms" 2>/dev/null; then
        continue
    fi
    printf -- '- %s\n' "$ssubj" >> "$work/$cat"
done <<EOF
$(git log "$range" --format=%s 2>/dev/null || true)
EOF

# --- Formatter --------------------------------------------------------------
block="$work/block"
{
    printf '## [Unreleased] - %s\n' "$date_str"
    for c in feat fix chore other; do
        if [ -s "$work/$c" ]; then
            printf '\n### %s\n' "$c"
            cat "$work/$c"
        fi
    done
} > "$block"

# --- CHANGELOG writer (atomic mktemp + mv) ----------------------------------
out="$work/out"
if [ ! -f CHANGELOG.md ]; then
    { cat "$block"; printf '\n'; } > "$out"
    mv "$out" CHANGELOG.md
else
    ur_line=$(grep -n '^## \[Unreleased\]' CHANGELOG.md | head -1 | cut -d: -f1 || true)
    if [ -n "$ur_line" ]; then
        echo "changelog: replacing existing [Unreleased] block in CHANGELOG.md" >&2
        rel_next=$(tail -n +"$((ur_line + 1))" CHANGELOG.md | grep -n '^## ' | head -1 | cut -d: -f1 || true)
        {
            if [ "$ur_line" -gt 1 ]; then head -n "$((ur_line - 1))" CHANGELOG.md; fi
            cat "$block"
            printf '\n'
            if [ -n "$rel_next" ]; then
                tail -n +"$((ur_line + rel_next))" CHANGELOG.md
            fi
        } > "$out"
        mv "$out" CHANGELOG.md
    else
        { cat "$block"; printf '\n'; cat CHANGELOG.md; } > "$out"
        mv "$out" CHANGELOG.md
    fi
fi

# --- Echo the generated block to stdout -------------------------------------
cat "$block"
```

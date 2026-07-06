#!/usr/bin/env bash
#
# bisect-resolve.sh — PRIVATE implementation detail of the /bisect command.
#
# This is NOT a shared utility. Do not depend on it from other commands or scripts;
# its interface may change with /bisect. It exists so the ticket-aware bisect logic
# (requirements.md FR-1..FR-12, NFR-1..NFR-3) can be unit-tested without an
# interactive bisect run.
#
# Contract notes:
#   * Every git invocation passes discrete argument lists — never string
#     interpolation into a shell (NFR-2). Ticket-number arguments are validated
#     against ^[0-9]{4}$ before any use, so an injection attempt such as
#     '0010; echo pwned' is rejected at the validation boundary and never reaches
#     a git command.
#   * The culprit-attribution output uses a UTF-8 em-dash (U+2014, the "—" below).
#     Callers/tests should run under LC_ALL=en_US.UTF-8 for a stable byte match.
#
# Subcommands: classify-boundary | resolve-boundary | resolve-ticket |
#              resolve-testcmd | wrap-testcmd | map-culprit | run
set -euo pipefail

die() { printf 'bisect-resolve: %s\n' "$*" >&2; exit 1; }

# ── FR-1/FR-2: boundary classification ────────────────────────────────────────
classify_boundary() {
    local value="${1-}"
    [ -n "$value" ] || die "classify-boundary: missing value"
    if [[ "$value" =~ ^[0-9]{4}$ ]]; then
        printf 'ticket\n'
    else
        printf 'ref\n'
    fi
}

# ── FR-3/FR-4: ticket number → merge commit SHA ───────────────────────────────
# Validation runs before any git use (FR-3, NFR-2). Resolution scans merge
# commits only and anchors the match to the subject line (FR-4), so a ticket
# mentioned only in another commit's body is not a false positive.
resolve_ticket() {
    local ticket="${1-}"
    [[ "$ticket" =~ ^[0-9]{4}$ ]] || die "invalid ticket number: ${ticket:-<empty>}"
    local line subject
    while IFS= read -r line || [ -n "$line" ]; do
        # subject-anchored: line is "<40-hex> <subject>"; require a Merge subject
        [[ "$line" =~ ^[0-9a-f]+[[:space:]]Merge ]] || continue
        subject="${line#* }"
        # word-boundary before "ticket/" (start of subject or a non-word char),
        # and the trailing '-' after the number prevents 0010 matching 00101-*
        if [[ "$subject" =~ (^|[^[:alnum:]_])ticket/${ticket}- ]]; then
            printf '%s\n' "${line%% *}"
            return 0
        fi
    done < <(git log --merges --pretty=format:'%H %s')
    die "no merge commit found for ticket ${ticket}"
}

# ── FR-1/FR-2/FR-3: resolve a boundary to a commit SHA ────────────────────────
resolve_boundary() {
    local value="${1-}"
    [ -n "$value" ] || die "resolve-boundary: missing value"
    if [ "$(classify_boundary "$value")" = ticket ]; then
        resolve_ticket "$value"
    else
        # Raw git ref: validate before bisect. The value is a single argv, so a
        # shell metacharacter in it cannot execute (NFR-2).
        git rev-parse --verify --quiet "${value}^{commit}" \
            || die "not a valid 4-digit ticket or git ref: ${value}"
    fi
}

# ── FR-6: resolve the test command string (precedence chain) ──────────────────
_settings_test_command() {
    # Extract the "test_command" key from a settings.json via python3 (stdlib
    # json), passing the path as argv. Empty output when absent/unparseable.
    python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
    v=d.get("test_command","")
    print(v if isinstance(v,str) else "")
except Exception:
    pass' "$1" 2>/dev/null || true
}

resolve_testcmd() {
    local run=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --run) [ $# -ge 2 ] || die "resolve-testcmd: --run requires a value"; run="$2"; shift 2 ;;
            *) die "resolve-testcmd: unknown argument: $1" ;;
        esac
    done
    # 1. explicit --run
    if [ -n "$run" ]; then printf '%s\n' "$run"; return 0; fi
    # 2. .claude/settings.json test_command
    if [ -f .claude/settings.json ]; then
        local sc; sc="$(_settings_test_command .claude/settings.json)"
        if [ -n "$sc" ]; then printf '%s\n' "$sc"; return 0; fi
    fi
    # 3. project auto-detect
    if [ -f package.json ]; then printf 'npm test\n'; return 0; fi
    if [ -f pyproject.toml ] && grep -qE '^\[tool\.pytest(\.ini_options)?\]' pyproject.toml; then
        printf 'pytest\n'; return 0
    fi
    # 4. no command determinable — fail closed with guidance (FR-6)
    die "no test command found. Pass --run <cmd>, set test_command in .claude/settings.json, or add package.json / a [tool.pytest] pyproject.toml section."
}

# ── FR-7: wrap a multi-word command in a single-path temp script ──────────────
# git bisect run takes a single executable path here. A command containing
# whitespace is wrapped in an mktemp script (its path is printed); a single-word
# command is printed unchanged. The temp script is the caller's to clean up
# (run() does so via its EXIT trap).
wrap_testcmd() {
    local cmd="${1-}"
    [ -n "$cmd" ] || die "wrap-testcmd: missing command"
    if printf '%s' "$cmd" | grep -q '[[:space:]]'; then
        local script; script="$(mktemp)"
        # Write the command into the wrapper body (data written to a file, not
        # interpolated into an executing shell). git bisect run invokes this path.
        printf '#!/usr/bin/env bash\n%s\n' "$cmd" > "$script"
        chmod +x "$script"
        printf '%s\n' "$script"
    else
        printf '%s\n' "$cmd"
    fi
}

# ── FR-10/FR-11: map a culprit commit back to a ticket ────────────────────────
_is_merge_commit() {
    # A merge commit has ≥2 parents → "<sha> <p1> <p2> ..." has ≥3 tokens.
    local parents; parents="$(git rev-list --parents -n 1 "$1")"
    [ "$(printf '%s' "$parents" | wc -w)" -ge 3 ]
}

_ticket_title() {
    # Print the title: field for a ticket, or nothing (fallback to bare number,
    # never an error — FR-11) when status.md is absent or the field missing.
    # Reads from git at the given tip rather than the working tree, because
    # during a bisect run the tree is checked out at the culprit commit (which
    # predates the ticket's status.md); the tip carries the current metadata.
    local ticket="$1" tip="${2:-HEAD}" path
    # `|| true` terminates the pipeline: when no status.md matches, grep exits 1
    # and, under `set -euo pipefail`, would otherwise abort map_culprit before it
    # prints the bare-number fallback line (FR-11: absent status.md must not error).
    path="$(git ls-tree -r --name-only "$tip" 2>/dev/null \
        | grep -E "^\.tickets/(completed/)?${ticket}-[^/]*/status\.md$" | head -1 || true)"
    [ -n "$path" ] || return 0
    git show "${tip}:${path}" 2>/dev/null | sed -n 's/^title:[[:space:]]*//p' | head -1
}

map_culprit() {
    local sha="${1-}"
    # Optional traversal tip (default HEAD). During a bisect run HEAD is detached
    # at the culprit, so run() passes the bad boundary as the tip to traverse
    # toward — otherwise the ancestry range would be empty.
    local tip="${2:-HEAD}"
    [ -n "$sha" ] || die "map-culprit: missing sha"
    local full; full="$(git rev-parse --verify --quiet "${sha}^{commit}")" \
        || die "map-culprit: not a commit: ${sha}"
    local ticket="" line subject
    # Direct case: the culprit is itself a ticket merge commit (FR-10).
    subject="$(git show -s --pretty=format:%s "$full")"
    if _is_merge_commit "$full" && [[ "$subject" =~ (^|[^[:alnum:]_])ticket/([0-9]{4})- ]]; then
        ticket="${BASH_REMATCH[2]}"
    else
        # Ancestry traversal: find the ticket merge commit that actually
        # introduced the culprit (FR-10). Among merges on the ancestry path, the
        # introducing merge is the one whose branch-side parent (^2) contains the
        # culprit while its mainline parent (^1) does not — this distinguishes a
        # commit that came in *through* the merged ticket branch from a commit
        # that merely predates a later merge. Branch containment is never the
        # sole mechanism.
        local msha
        while IFS= read -r line || [ -n "$line" ]; do
            [[ "$line" =~ ^[0-9a-f]+[[:space:]]Merge ]] || continue
            msha="${line%% *}"
            subject="${line#* }"
            [[ "$subject" =~ (^|[^[:alnum:]_])ticket/([0-9]{4})- ]] || continue
            if git merge-base --is-ancestor "$full" "${msha}^2" 2>/dev/null \
               && ! git merge-base --is-ancestor "$full" "${msha}^1" 2>/dev/null; then
                ticket="${BASH_REMATCH[2]}"; break
            fi
        done < <(git log --merges --ancestry-path --pretty=format:'%H %s' "${full}..${tip}")
    fi
    # NFR-3: no ticket merge commit found → report the raw SHA, no error.
    if [ -z "$ticket" ]; then
        printf 'Regression introduced in commit %s — not linked to a ticket\n' "$full"
        return 0
    fi
    local title; title="$(_ticket_title "$ticket" "$tip")"
    if [ -n "$title" ]; then
        printf 'Regression introduced in commit %s — part of ticket %s (%s)\n' "$full" "$ticket" "$title"
    else
        printf 'Regression introduced in commit %s — part of ticket %s\n' "$full" "$ticket"
    fi
}

# ── FR-5/FR-8/FR-9/FR-12/NFR-1: full orchestration ────────────────────────────
cmd_run() {
    local good="" bad="HEAD" run=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --good) [ $# -ge 2 ] || die "run: --good requires a value"; good="$2"; shift 2 ;;
            --bad)  [ $# -ge 2 ] || die "run: --bad requires a value";  bad="$2";  shift 2 ;;
            --run)  [ $# -ge 2 ] || die "run: --run requires a value";  run="$2";  shift 2 ;;
            *) die "run: unknown argument: $1" ;;
        esac
    done
    [ -n "$good" ] || die "run: --good <ticket-or-ref> is required"

    # Resolve everything BEFORE starting bisect so a bad boundary or missing test
    # command errors before any bisect state exists (FR-3/FR-4/FR-6).
    local good_sha bad_sha testcmd
    good_sha="$(resolve_boundary "$good")"
    bad_sha="$(resolve_boundary "$bad")"
    if [ -n "$run" ]; then testcmd="$(resolve_testcmd --run "$run")"; else testcmd="$(resolve_testcmd)"; fi

    TMPSCRIPT=""
    local execpath; execpath="$(wrap_testcmd "$testcmd")"
    # wrap_testcmd only returns a path different from the command when it wrapped.
    if [ "$execpath" != "$testcmd" ]; then TMPSCRIPT="$execpath"; fi

    # Sole cleanup path (FR-12/NFR-1): fires on success (git bisect run exit 1),
    # setup error, and interrupt. `|| true` avoids a double-fire "We are not
    # bisecting" non-zero exit when the repo is already reset. Removes the temp
    # wrapper too (FR-7).
    trap 'git bisect reset >/dev/null 2>&1 || true; [ -n "${TMPSCRIPT:-}" ] && rm -f "${TMPSCRIPT}" 2>/dev/null || true' EXIT

    git bisect start >/dev/null
    git bisect bad "$bad_sha" >/dev/null
    git bisect good "$good_sha" >/dev/null

    # FR-8: git bisect run drives good/bad from the test exit code (0=good,
    # non-zero=bad). Convergence is signalled by the "<sha> is the first bad
    # commit" line — the sole reliable indicator across git versions and the only
    # thing that means a culprit was actually found. A non-converging run (an
    # abort from a test exit >=128, or an all-skip) prints no such line; we must
    # NOT fall back to refs/bisect/bad (which merely holds the bad boundary mid
    # bisect) and report it as a bogus culprit.
    local out bisect_rc=0 culprit
    out="$(git bisect run "$execpath" 2>&1)" || bisect_rc=$?
    culprit="$(printf '%s\n' "$out" | sed -n 's/^\([0-9a-f]\{7,40\}\) is the first bad commit.*$/\1/p' | head -1)"
    if [ -z "$culprit" ]; then
        printf '%s\n' "$out" >&2
        die "run: bisect did not converge to a culprit (git bisect run exited ${bisect_rc})"
    fi

    # FR-9/FR-11: report the culprit SHA and ticket attribution. HEAD is detached
    # at the culprit right now, so traverse toward the bad boundary instead.
    map_culprit "$culprit" "$bad_sha"
}

main() {
    local sub="${1-}"; shift || true
    case "$sub" in
        classify-boundary) classify_boundary "$@" ;;
        resolve-boundary)  resolve_boundary "$@" ;;
        resolve-ticket)    resolve_ticket "$@" ;;
        resolve-testcmd)   resolve_testcmd "$@" ;;
        wrap-testcmd)      wrap_testcmd "$@" ;;
        map-culprit)       map_culprit "$@" ;;
        run)               cmd_run "$@" ;;
        ""|-h|--help)
            printf 'usage: bisect-resolve.sh <classify-boundary|resolve-boundary|resolve-ticket|resolve-testcmd|wrap-testcmd|map-culprit|run> ...\n' ;;
        *) die "unknown subcommand: $sub" ;;
    esac
}

main "$@"

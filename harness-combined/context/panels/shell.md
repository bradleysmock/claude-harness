## Shell & Bash Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Greg Wooledge** — maintainer of BashFAQ and the Bash Pitfalls page (mywiki.wooledge.org); the de facto encyclopedia of "things shell scripts get wrong"
- **Chet Ramey** — bash maintainer (Case Western Reserve); POSIX vs bash semantics, shell internals, what the standard actually says

**Wooledge's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Always quote your variables** | `rm $file` where `$file` is `"my document.txt"` runs `rm my document.txt` — two arguments. The quoting rule is not stylistic; it is the difference between working and deleting the wrong thing. Quote every variable expansion that isn't deliberately word-split. |
| **Use arrays for lists, not space-separated strings** | `files="a b c"; for f in $files` works only if no filename contains a space, a tab, or a glob character. `files=(a b c); for f in "${files[@]}"` works always. |
| **Don't parse `ls`** | `for f in $(ls)` breaks on whitespace, newlines in filenames, and glob characters. Use a glob (`for f in *`) or `find -print0 \| xargs -0`. |
| **`[[ ]]` over `[ ]` in bash** | `[[ ]]` is a bash keyword with sane parsing: no word splitting on unquoted expansions, regex matching, glob matching. `[ ]` is a program with shell-parsed arguments — every footgun is in scope. |
| **`set -e` is a fragile tool** | It changes behavior in nested contexts (functions, subshells, command substitution) in ways the manual itself describes with caveats. Useful, but not a substitute for explicit `\|\|` error handling. |
| **`mapfile` / `readarray` over `while read` loops where possible** | The `while IFS= read -r line; do ... done < file` pattern works; `mapfile -t lines < file` is harder to get wrong. |

**Ramey's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **`#!/bin/sh` is not bash** | A script with `#!/bin/sh` runs under POSIX sh on most modern systems (dash on Debian/Ubuntu, ash on Alpine). Bash-isms (`[[ ]]`, arrays, `==`, `$'...'`, `local`) will silently misbehave or fail. Match the shebang to the features. |
| **Subshells discard variable changes** | `echo x \| while read line; do count=$((count+1)); done; echo $count` — `count` is 0. The right side of a pipe runs in a subshell. Use process substitution (`< <(...)`), `lastpipe`, or restructure. |
| **`local` is bash-specific and required in functions** | Without `local`, every variable assignment in a function is global. Refactors at distance break unrelated code. POSIX sh has no `local` — write functions accordingly. |
| **`printf` is portable; `echo` is not** | `echo -n`, `echo -e`, and backslash escapes behave differently across shells and even bash builds. `printf '%s' "$x"` is unambiguous. |
| **Word splitting and globbing happen *after* expansion** | Unquoted `$var` is split on `$IFS`, then each word is globbed. `IFS` defaults to space/tab/newline. This is the single most common source of bugs in shell scripts. |

*Synthesis:* Wooledge catalogues the failure modes — what goes wrong when you don't quote, when you parse output, when you assume your inputs are tame. Ramey is the authority on what the shell *actually does* — POSIX vs bash, subshell semantics, expansion order. Most "weird shell bugs" are one of: an unquoted variable, a subshell that lost the change, or a script with the wrong shebang for its features.

---

## Review Dimensions

---

### Dimension 29: Shell Script Correctness & Safety
*Wooledge, Ramey*

| Hazard | What to look for |
|--------|-----------------|
| **Missing `set -euo pipefail`** | Script without `set -e` (exit on error), `set -u` (unset variables are errors), and `set -o pipefail` (pipeline status reflects any failing stage). Errors silently ignored. |
| **Unquoted variable expansion** | `rm $file`, `cd $dir`, `if [ $x = y ]` — word-splits and globs `$x`. Use `"$file"`, `"$dir"`, `[[ $x == y ]]`. |
| **`rm -rf "$VAR/"` with possibly empty `VAR`** | If `VAR=""`, becomes `rm -rf "/"`. Always check `[[ -n $VAR ]]` first, or use `${VAR:?required}`. |
| **`[ ]` instead of `[[ ]]`** | `[ -z $x ]` with unquoted `$x` empty becomes `[ -z ]` — a syntax error. `[[ -z $x ]]` works. Prefer `[[ ]]` in bash; if targeting POSIX sh, always quote. |
| **`for x in $list`** | Word-splits `$list` on `$IFS` and globs each result. Use `for x in "${arr[@]}"` with an array. |
| **Parsing `ls` output** | `for f in $(ls)`, `ls \| grep ...`, `wc -l < $(ls)` — breaks on spaces, newlines, glob chars in filenames. Use globs or `find -print0 \| xargs -0`. |
| **`cd` without `\|\|`** | `cd /some/dir; rm -rf *` — if `cd` fails, `rm` runs in the current directory. Use `cd /some/dir \|\| exit 1` or `cd /some/dir \|\| return 1`. |
| **`eval` on any user-influenced string** | `eval "$cmd"` where `$cmd` came from anywhere outside the script itself. Code injection. |
| **Variable assignment in a subshell** | `cmd \| while read x; do COUNT=$((COUNT+1)); done` — `COUNT` is unchanged after the loop. Use `< <(cmd)`, `shopt -s lastpipe`, or accumulate into a file. |
| **Function variables not `local`** | Variables assigned in a bash function without `local` declaration leak to the global scope. Refactors elsewhere mysteriously break. |
| **POSIX shebang with bash features** | `#!/bin/sh` followed by `[[ ]]`, arrays, `==`, `local`, `$'...'`, `<<<`, etc. Works on systems where `/bin/sh` is bash; fails on dash/ash. Match shebang to features. |
| **`read` without `-r`** | `read line` interprets backslashes. `read -r line` doesn't. Always `-r` unless you genuinely want escape processing. |
| **`mktemp` not used for temp files** | Hardcoded `/tmp/myfile` — race condition, symlink attack vector, collision. Use `mktemp` and clean up with `trap`. |
| **Missing `trap` for cleanup** | Script that creates temp files / directories / locks with no `trap 'rm -rf "$tmpdir"' EXIT` to clean up on any exit path. |
| **`echo` for arbitrary data** | `echo "$x"` where `$x` may start with `-` or contain backslashes. Use `printf '%s\n' "$x"`. |
| **`if cmd && other` used as if/else** | `mkdir x && cd x \|\| exit` — operator precedence and short-circuit semantics make this read different than it executes. Use explicit `if`/`then`/`else`/`fi`. |
| **Command substitution losing exit status** | `result=$(cmd)` — `$?` after this is `cmd`'s status, but `set -e` doesn't trigger on it in all bash versions. Check explicitly when correctness matters. |
| **`$@` vs `$*`** | `"$@"` preserves arguments as separate words; `"$*"` joins on the first character of `$IFS`. Almost always you want `"$@"`. |
| **Shellcheck disabled without reason** | `# shellcheck disable=SC2086` without a same-line comment justifying why the warning is wrong for this case. Every suppression needs a reason. |
| **Implicit dependency on tool versions** | `grep -P`, `sed -i`, `date -d`, `xargs --no-run-if-empty` — GNU extensions not portable to BSD/macOS. Either depend deliberately and document, or use portable forms. |
| **Pipeline of long-running stages without `pipefail`** | A pipeline where the first stage's failure should kill the script — but without `set -o pipefail`, only the last stage's status counts. |
| **Concatenating commands into a string then running** | `cmd="rm -rf $dir"; $cmd` or `bash -c "$cmd"` — shell parses the result, reintroducing word splitting and glob expansion on `$dir`. Use arrays: `cmd=(rm -rf "$dir"); "${cmd[@]}"`. |

Wooledge's design question: have you run `shellcheck` on this script and either fixed or justified every warning?

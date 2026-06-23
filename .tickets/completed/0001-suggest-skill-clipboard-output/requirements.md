# Requirements

**Ticket**: 0001
**Title**: Suggest skill: copy output to clipboard and write to suggestions.txt

## Functional Requirements

1. The system must write the full suggestions table (all groups) to `suggestions.txt` in the working directory immediately after Step 7 displays it.
2. The system must copy the suggestions table to the system clipboard immediately after writing the file.
3. When accepted `/problem` lines are emitted (Step 8), they must be appended to `suggestions.txt` below the table.
4. The system must inform the lead that the file has been written and clipboard has been populated (single confirmation line per action).
5. Each run must overwrite `suggestions.txt` (not append to prior runs) — the file reflects the current session only.
6. The system must not write `suggestions.txt` or perform any clipboard action when no suggestions pass deduplication (Step 6 removes all candidates).

## Non-Functional Requirements

1. Clipboard copy uses `pbcopy` on macOS; the skill must attempt it via a Bash tool call and silently skip if the command is unavailable.
2. File write uses the Write tool (not shell redirection).

## Test Strategy

| Type        | Rationale                                           |
|-------------|-----------------------------------------------------|
| Unit        | Verify file content matches suggestions table text  |
| Integration | Verify clipboard receives the suggestions text      |

## Acceptance Criteria

- `suggestions.txt` exists in the working directory after `/suggest` completes with at least one suggestion.
- `suggestions.txt` contains the formatted suggestions table.
- `suggestions.txt` contains accepted `/problem` lines (if any were accepted).
- Clipboard contains the suggestions table text.
- Lead sees a single confirmation line per output action (file + clipboard).
- Running `/suggest` a second time overwrites `suggestions.txt`.

## Open Questions

- None.

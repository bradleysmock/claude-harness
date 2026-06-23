# Problem Statement

**Ticket**: 0001
**Title**: Suggest skill: copy output to clipboard and write to suggestions.txt
**Date**: 2026-06-22

## Problem

The `/suggest` skill produces a formatted suggestion table and `/problem`-ready lines that the lead must manually capture. There is no automated way to persist or transfer this output — the lead must copy from the terminal manually, which is friction-prone and error-prone.

## Impact

- Lead engineers lose suggestions if they clear the terminal or switch sessions before capturing them.
- Manual copy-paste slows the flow from `/suggest` acceptance to `/problem` invocation.
- No file record means suggestions cannot be reviewed, shared, or referenced later.

## Success Criteria

- After Step 7 (display suggestions table), the full suggestions section is written to `suggestions.txt` in the working directory.
- After Step 8 (emit accepted `/problem` lines), those accepted lines are also appended to `suggestions.txt`.
- The suggestions output is copied to the system clipboard automatically.
- The lead is informed that both actions (file write + clipboard copy) have occurred.

## Out of Scope

- Changes to the suggestion generation logic (Steps 1–6).
- Persistent history across multiple runs (each run overwrites `suggestions.txt`).
- Clipboard behavior on non-macOS platforms beyond a best-effort attempt.

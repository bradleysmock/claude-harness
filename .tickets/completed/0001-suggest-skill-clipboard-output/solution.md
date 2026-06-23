# Solution

**Ticket**: 0001
**Title**: Suggest skill: copy output to clipboard and write to suggestions.txt

## Approach

Add two output actions at the end of Step 7 (after presenting the suggestions table) and one at the end of Step 8 (after emitting accepted `/problem` lines): write to `suggestions.txt` via the Write tool, copy to clipboard by redirecting `suggestions.txt` into `pbcopy`, and print a single confirmation line per action. No changes to Steps 1–6 (detection, inventory, deduplication). Step 7 extensions run only when the deduplicated candidate list is non-empty — the existing Step 6 no-candidates stop path is the guard.

## Components

| Component | Responsibility | Interface |
|-----------|----------------|-----------|
| Step 7 extension | Write suggestions table to `suggestions.txt`; copy to clipboard; confirm to lead | Write tool + Bash (`pbcopy < suggestions.txt`) |
| Step 8 extension | Read `suggestions.txt`, append accepted `/problem` lines, overwrite with combined content | Write tool (read-then-overwrite) |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Write tool for file | Consistent with harness patterns; no shell injection risk |
| `pbcopy < suggestions.txt` via Bash | File redirect avoids any shell variable or string interpolation — no metacharacter exposure regardless of suggestion content; `suggestions.txt` is always written immediately before this call |
| `command -v pbcopy` guard | Wraps clipboard call — if `pbcopy` absent, skip silently with no error output |
| Read-then-overwrite for Step 8 | Reads `suggestions.txt` at Step 8 to source the table text; avoids relying on in-memory recall between steps |
| Overwrite on each run | Keeps `suggestions.txt` current; avoids stale-data confusion from prior runs |
| `suggestions.txt` format is internal | File layout (table then `/problem` lines) is not a stable versioned interface; subject to change |

## Test Plan

| Requirement | Test Type   | Scenario(s)                                              |
|-------------|-------------|----------------------------------------------------------|
| FR-1        | Automated   | Run skill with ≥1 candidate; assert `suggestions.txt` exists and contains table text |
| FR-2        | Manual checklist | Pre-shipment: run skill, then verify `pbpaste \| diff - suggestions.txt` produces no diff (table portion); reviewer signs off in PR |
| FR-3        | Automated   | Accept a suggestion; assert `suggestions.txt` contains both table and `/problem` line |
| FR-4        | Manual      | Verify confirmation lines appear in output               |
| FR-5        | Automated   | Run skill twice; assert second run's file does not contain first run's content |
| FR-6        | Automated   | Simulate zero post-dedup candidates; assert Write tool is never called |

Note: FR-2 clipboard automation is excluded — headless clipboard assertion is not available in the harness test environment. FR-2 is treated as a best-effort side-effect; the acceptance criterion requires a signed pre-shipment manual check, not automated verification.

## Acceptance Criteria (revised)

- `suggestions.txt` exists after `/suggest` completes with ≥1 suggestion.
- `suggestions.txt` contains the formatted suggestions table.
- `suggestions.txt` contains accepted `/problem` lines below the table (if any accepted).
- Lead sees one confirmation line after file write and one after clipboard copy (Step 7 only).
- Running `/suggest` a second time overwrites `suggestions.txt`.
- **Clipboard (best-effort)**: clipboard is populated when `pbcopy` is available; verified by pre-shipment manual check (`pbpaste | diff - suggestions.txt` on table portion).

## Tradeoffs

- **Chose `pbcopy < suggestions.txt` over variable approach**: file redirect is unconditionally safe — no shell quoting, no escape handling, no metacharacter exposure; variable approach would require correct quoting of model-generated content.
- **Chose overwrite over append across runs**: appending would accumulate stale suggestions; overwrite keeps the file focused on the current session.
- **Accepting risk of partial Step 8 write**: if Step 8 overwrite fails after Step 7 succeeded, `suggestions.txt` retains the table but lacks accepted `/problem` lines. The lead's Step 7 confirmation is still accurate ("written to suggestions.txt and copied to clipboard") — the Step 7 actions completed. Step 8's failure produces no corrective signal. This is acceptable since accepted lines are also visible in the terminal output.

## Risks

- `pbcopy` is macOS-only — mitigated by `command -v pbcopy` guard; skip is silent.
- Step 8 overwrite failure leaves `suggestions.txt` without accepted lines — acceptable; accepted lines remain visible in terminal.
- `suggestions.txt` file layout will become an implicit contract if leads script against it — noted as internal/non-versioned; enforce change communication if format changes.

## Implementation Order

1. **Precondition guard (Step 7 entry)**: confirm deduplicated list is non-empty before proceeding; existing Step 6 no-candidates path already stops execution so file-write and clipboard actions are unreachable from that path — state this guard explicitly in the skill.
2. **Step 7 extension — write file**: after displaying the suggestions table, write the full table text to `suggestions.txt` using the Write tool.
3. **Step 7 extension — clipboard**: run `command -v pbcopy >/dev/null 2>&1 && pbcopy < suggestions.txt` via Bash tool; if `pbcopy` is absent, the guard short-circuits silently with no error.
4. **Step 7 extension — confirm**: print one line: `Suggestions written to suggestions.txt and copied to clipboard.`
5. **Step 8 extension — overwrite with combined content**: after emitting accepted `/problem` lines, read the current `suggestions.txt` content, append the accepted lines below, and overwrite `suggestions.txt` with the combined content via Write tool.
6. **Step 8 extension — confirm**: print one line: `suggestions.txt updated with accepted /problem lines.`
7. **Step 9 update**: note that `suggestions.txt` and clipboard are populated as side-effects; clipboard copy is best-effort (macOS `pbcopy` only).

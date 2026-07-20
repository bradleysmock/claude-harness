# Critic Findings — 0068-slim-deliver-ticket

## Round 1 — 2026-07-20

**Panels active:** Core (always active) + Python (`ticket.py`, `learnings.py` in scope) + Testing (new/modified test files in scope). No gate-findings.md exists yet for this ticket, so Step 2 of the brief is a no-op this round.

### BLOCKER

**BLOCKER-1 — `sanitize_pattern`'s directive-token match is not actually depunctuated — possessive/contracted forms bypass the filter.** `_WORD_RE = re.compile(r"[A-Za-z0-9']+")` retains the apostrophe as part of a matched word, so `"Claude's"` tokenizes to `"claude's"`, which never equals `"claude"`, and the sentence is not stripped. FR-6 requires the token to be "lowercased, depunctuated" before the set comparison. Fix: strip the apostrophe from the word-char class so `"Claude's"` splits into `"claude"` + `"s"`.

### MAJOR

**MAJOR-1 — `_parse_critic_findings`'s rigid template is not actually guaranteed by the critic's output contract.** `_CRITIC_ENTRY_RE` required the exact `**BLOCKER-N — summary.**` template (numbered, em-dash, trailing period), but `critic-brief.md` Step 4 never mandates this literal markdown shape — only severity tier, panel/dimension, file:line, and a one-paragraph statement. A differently-formatted-but-conformant critic round could be silently dropped. Fix: widen the regex to tolerate reasonable punctuation variance (colon/hyphen separator, no numeric suffix, no trailing period).

**MAJOR-2 — deliver-ticket.md Step 5's cross-source "re-sort by severity then recency" is unimplementable from the data the CLI actually returns.** `parse_findings()`'s returned record shape carries no recency/order field once returned — `order` is internal-only and discarded before return. Fix: rewrite the merge instruction as concatenate + dedup on `(gate, pattern)` + stable severity-only sort + cap at 5 (drop the unimplementable recency claim).

### MINOR

**MINOR-1 — gate bullet fallback keeps the raw bullet as `message` rather than truly "skipping" it**, per `parse-gate-findings.md`'s Step 2 tolerant-skip wording — harmless in practice but the doc and code disagree on the exact tolerance semantics.

### OBS

**OBS-1 — CLI usage string doesn't mention `deliver_squash()`/`deliver_squash_batch()` remain Python-only entry points** with no direct CLI verb — consistent with the design, just worth noting for a future reader.

No other requirements-coverage or solution-alignment gaps found: FR-1/2/3, FR-4, FR-7, and NFR-2 verified as correctly implemented and tested.

## Round 2 — 2026-07-20

**Panels active:** Core (always active). Python lens applies (`learnings.py`, `tests/test_learnings_module.py`).

### Disposition of Round 1 findings

- **BLOCKER-1 — RESOLVED.** `_WORD_RE` changed to `r"[A-Za-z0-9]+"`; traced `_sentence_has_directive` — `"Claude's directive..."` now tokenizes to `{"claude", "s"}`, which intersects the directive set. Confirmed against the new regression test. No new false positives from the widened word class (contraction fragments like `don`/`t` never collide with the six-token set).
- **MAJOR-1 — RESOLVED for the stated punctuation-variance gap, with one residual OBS note (see below).** The widened `_CRITIC_ENTRY_RE` still correctly rejects MINOR/OBS-only content (the alternation only matches literal `BLOCKER`/`MAJOR`), doesn't introduce new false-positive matches against ordinary bolded prose in the flow docs, and the real historical `critic-findings.md` sample (ticket 0042) still matches — backward compatible.
- **MAJOR-2 — RESOLVED.** deliver-ticket.md Step 5 now specifies a fully mechanical, implementable procedure (concatenate gate-then-critic, dedup on `(gate, pattern)` keeping first occurrence, stable-sort by severity only, cap at 5), internally consistent with `parse_findings`'s actual return contract.

### OBS

**OBS-1 — `_CRITIC_ENTRY_RE`'s tolerance is still contingent on the critic wrapping each finding in `**...**`**, which `critic-brief.md` Step 4 and `agents/critic.md` do not actually mandate (only severity tier, panel/dimension, file:line, and a one-paragraph statement). A plain `BLOCKER: ...` (no bold wrapper) round would still silently fail to parse — same root cause as MAJOR-1, narrower in practice. Out of this ticket's stated `Components` scope (`ticket.py`, `learnings.py`, named flow docs only); every observed historical sample uses the bold convention. Recommend a follow-up ticket to pin the bold-template convention in `critic-brief.md` Step 4.

### MINOR

**MINOR-2 — Documented "fallback to first sentence of detail prose" (parse-gate-findings.md Step 2c) is unimplemented** in `_parse_critic_findings` — predates Round 1's repair, consistent with the tolerant-skip philosophy elsewhere in the flow, not elevated.

**MINOR-3 — Step 5's cross-source merge/dedup/sort/cap is executed as flow-doc prose, not a tested `learnings.py` function**, in tension with the ticket's "move mechanics behind ticket.py" purpose — but `solution.md`'s CLI table never planned a `merge` subcommand, a Checkpoint-1-approved scope boundary, not a Round 1 regression. Logged as a future-ticket candidate.

### Summary

BLOCKER-1, MAJOR-1, and MAJOR-2 are all resolved by the Round 1 repair; no new BLOCKER or MAJOR findings. Two MINOR/OBS-level notes are worth a follow-up ticket but do not block delivery.

Iterate on the solution design before implementation. Manual escape hatch for additional refinement passes.

## Ticket Resolution

If a ticket number is provided as an argument, scan `.tickets/<arg>*/` first, then `.tickets/completed/<arg>*/` if not found. Otherwise scan `.tickets/` for tickets with `status: solution`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. Read `problem.md`, `requirements.md`, and `solution.md` in full.

2. Proactively surface anything that could cause problems in implementation:
   - Ambiguous requirements the solution doesn't fully address
   - Edge cases not covered in the test plan
   - Implementation details not yet decided (data schemas, API contracts, error handling)
   - Missing test scenarios
   - Dependencies or sequencing risks in the implementation order

3. For each item, propose specific options with tradeoffs rather than asking open-ended questions.

4. After each resolved item, update `solution.md` to reflect the decision. Track unresolved items in an Open Questions section.

5. Status stays at `solution` — `/refine` can be run multiple times. If you revised `solution.md` (or any artifact), commit the change to `main` so it is not left local-only (scoped add — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

```
git add .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX refine solution"
```

If no artifact was changed this pass, skip the commit.

6. When satisfied, suggest `/write-spec XXXX` to formalize the solution into specs, then `/build XXXX` to begin implementation.

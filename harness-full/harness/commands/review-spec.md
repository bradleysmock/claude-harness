# /review-spec

Review a harness spec file for completeness before submission.

Read the spec file, then read every file in its `reference_files` and the
directory containing `target_file`.

## Checklist

**Correctness**
- [ ] Referenced classes/methods actually exist at those paths
- [ ] API signatures in constraints match actual source
- [ ] target_file path is consistent with codebase structure

**Completeness**
- [ ] Every constraint names specific code — not vague patterns
- [ ] Every acceptance criterion is a single testable assertion
- [ ] Error paths are covered — not just happy path
- [ ] Implementation would know what to import from where

**Consistency**
- [ ] Constraints and acceptance criteria agree with each other
- [ ] Spec agrees with patterns visible in reference_files
- [ ] No implicit constraints in reference_files are missing from spec

## Output

**READY** — spec is complete. No changes needed.

**NEEDS REVISION** — list specific issues:
  - Issue: what is wrong or missing
  - Fix: the exact text to add or change

Do not edit the spec file directly.

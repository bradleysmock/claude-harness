Gather and document requirements for a ticket. Manual escape hatch — the automated `/problem` flow runs this internally.

## Ticket Resolution

If a ticket number is provided as an argument, use it. Otherwise scan `.tickets/` for tickets with `status: problem` or `status: requirements`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. Read `problem.md` for the resolved ticket before proceeding.

2. Derive requirements from the problem statement. Flag genuine blockers in the Open Questions section rather than stopping — do not ask questions for the sake of it.

3. Write `requirements.md`:

```markdown
# Requirements

**Ticket**: XXXX
**Title**: <title>

## Functional Requirements

<Numbered list. Each item is a testable statement: "The system must...">

## Non-Functional Requirements

<Numbered list. Include performance, security, accessibility as applicable. Omit if none.>

## Tech Stack

<Only for new applications. Language, runtime, frameworks, tooling.>

## Test Strategy

| Type        | Rationale                          |
|-------------|------------------------------------|
| Unit        | <what is tested at unit level>     |
| Integration | <what is tested at integration>    |

## Acceptance Criteria

<Bullet list. Binary pass/fail.>

## Open Questions

<Genuine blockers that cannot be reasonably inferred. Empty if none.>
```

4. Update `status.md` to `status: requirements`.

5. Commit the metadata transition to `main` (scoped add — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

```
git add .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX → requirements"
```

6. If there are open questions, surface them to the lead. Otherwise suggest `/solution`.

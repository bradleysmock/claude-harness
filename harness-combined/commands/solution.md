Propose a solution design for a ticket. Manual escape hatch — the automated `/problem` flow runs this internally.

## Ticket Resolution

If a ticket number is provided as an argument, use it. Otherwise scan `.tickets/` for tickets with `status: requirements`. If exactly one exists, use it. If multiple exist, list them and require the lead to specify one before continuing.

## Steps

1. Read `problem.md` and `requirements.md` in full. If there are unresolved open questions in requirements, raise them before proceeding.

2. Draft the solution covering: approach, components, tech choices with rationale, test plan, tradeoffs, risks, and implementation order.

3. Write `solution.md` directly:

```markdown
# Solution

**Ticket**: XXXX
**Title**: <title>

## Approach

<2–4 sentences describing the solution at a high level.>

## Components

<Table or bullet list: component name, responsibility, key interfaces>

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| ...    | ...       |

## Test Plan

| Requirement | Test Type   | Scenario(s)            |
|-------------|-------------|------------------------|
| FR-1        | Unit        | <what is tested>       |
| FR-2        | Integration | <what is tested>       |

## Tradeoffs

- **Chose X over Y because**: ...
- **Accepting risk of**: ...

## Risks

<Bullet list with mitigations where known.>

## Implementation Order

<Ordered list of implementation steps. This is what /build uses to determine spec order.>
```

4. Update `status.md` to `status: solution`.

5. Offer `/refine` if further iteration is needed, or suggest `/write-spec XXXX` then `/build XXXX` when ready.

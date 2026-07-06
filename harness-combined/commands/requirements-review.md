Invoke the requirements-review skill to validate a ticket's requirements integrity before /build — reads problem.md and requirements.md for the given ticket, evaluates completeness, testability, coverage, and consistency in a scoped read-only subagent, and writes an advisory `requirements-findings.md`.

Argument: the four-digit ticket number (e.g. `/requirements-review 0034`).

Use the Skill tool to load and follow `requirements-review`, passing the ticket number as its argument.

# Requirements

**Ticket**: FIXTURE
**Title**: Report generation (coverage-defect fixture)

## Functional Requirements

1. The system must write a populated report when input data is present.
2. The system must write the report to the configured output path.

## Acceptance Criteria

- A run over 5 input records produces a report listing all 5.
- The report is written to the path given by the --out flag.

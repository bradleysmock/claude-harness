# Problem Statement

**Ticket**: 0002
**Title**: Feature Suggestion Skill
**Date**: 2026-06-20

## Problem

The harness has no mechanism for discovering what features to build next. Users must manually survey the codebase, review planned tickets, and compare against similar tools to identify gaps — an unstructured process that misses obvious improvements and produces no actionable output. A dedicated skill would make feature discovery repeatable and low-friction.

## Impact

- Lead spends unstructured time deciding what to build next, with no audit trail
- Obvious improvements visible in similar tools or business domains go unnoticed
- When the lead does identify an improvement, converting it to a ticket is a separate manual step

## Success Criteria

- Skill assesses what is currently implemented and what is planned (open tickets)
- Skill surfaces comparable apps / business-domain patterns to identify gaps
- Output is a ranked or grouped list of potential improvements, each with a brief summary
- Lead can accept individual suggestions; each accepted suggestion is converted to a ticket via `/problem`
- Skill is usable even when project documentation outside `.tickets/` is sparse

## Out of Scope

- Automatic ticket creation without lead approval
- Deep codebase analysis beyond surface-level feature inventory
- Suggestions for the harness infrastructure itself (only product/skill-level improvements)

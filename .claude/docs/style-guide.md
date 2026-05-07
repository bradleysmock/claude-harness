# Code Style Guide

This style guide is injected into every Stage 3 generation prompt. It defines the non-negotiable style requirements for all generated code.

---

## Universal Rules (All Languages)

### Naming
- **Functions/methods:** `verb_noun` — describe the action: `get_user`, `validate_token`, `send_email`
- **Variables:** descriptive nouns, no single letters except loop indices
- **Constants:** `UPPER_SNAKE_CASE`
- **Booleans:** prefix with `is_`, `has_`, `can_`, `should_`: `is_valid`, `has_permission`
- **Avoid:** `data`, `info`, `result`, `temp`, `obj`, `thing`, `stuff`

### Functions
- Maximum 30 lines (excluding docstring)
- Maximum cyclomatic complexity: 10
- Maximum parameters: 5 (use a dataclass/struct for more)
- Single responsibility: if you can't describe it without "and", split it
- Return early to avoid deep nesting; prefer guard clauses

### Error Handling
- Never swallow exceptions silently
- Always specify the exception type being caught
- Log enough context to debug without logging sensitive data
- Use domain-specific exception types; never raise generic `Exception`

### Constants & Configuration
- No magic numbers — every literal value must be a named constant
- No magic strings — use enums or constants for string literals that carry meaning
- No hardcoded configuration — use environment variables or config files

### Documentation
- Every public function/class must have a docstring
- Inline comments: explain *why*, not *what* (the code shows what)
- Complexity annotations for anything non-obvious

---

## Python-Specific

```
# Style target: PEP 8 + Black + strict mypy
# Line length: 99 characters
# Quote style: double quotes

from __future__ import annotations

from typing import TYPE_CHECKING
import stdlib_modules

import third_party_packages

import local_modules

if TYPE_CHECKING:
    from typing import ...
```

- **Type annotations:** required on all function signatures; use `X | None` not `Optional[X]`
- **Dataclasses:** prefer `@dataclass(frozen=True)` for value objects
- **Protocols:** use for dependency injection; avoid ABCs unless serialisation requires them
- **Exceptions:** define custom exception classes in `src/exceptions.py`
- **No `*` imports** — explicit imports only
- **`__all__`:** define in every public module

---

## TypeScript-Specific

```typescript
// Target: ES2022, strict mode, no implicit any
// Module system: ESM
// Style: Prettier defaults

// Imports: stdlib → third-party → local → types
import fs from 'node:fs/promises';
import { z } from 'zod';
import { UserRepository } from './repositories.js';
import type { User } from './types.js';
```

- **Strict mode:** `"strict": true` in tsconfig — no exceptions
- **No `any`:** use `unknown` and narrow; document every `as` cast with a comment
- **Zod or equivalent** for runtime validation of external inputs
- **`readonly`:** mark all properties readonly unless mutation is intentional
- **Enums:** prefer `const` object with `as const` over TypeScript enums
- **Error handling:** use `Result<T, E>` pattern or typed error classes

---

## Go-Specific

- Follow `gofmt` — no deviations
- Error handling: always handle errors; never use `_` to discard errors
- Package names: single lowercase word; no underscores
- Interface names: verb-er suffix where idiomatic (`Reader`, `Storer`)
- Avoid init() functions

---

## Anti-patterns (Never Generate These)

```python
# ❌ Magic numbers
if retry_count > 3:  # What is 3? Why 3?

# ✅
MAX_RETRY_ATTEMPTS = 3
if retry_count > MAX_RETRY_ATTEMPTS:

# ❌ Swallowed exception
try:
    do_thing()
except Exception:
    pass

# ✅
try:
    do_thing()
except SpecificError as exc:
    logger.error("Failed to do_thing: %s", exc, exc_info=True)
    raise

# ❌ Boolean parameter
def send(user, is_urgent):

# ✅
def send(user: User) -> None:
def send_urgent(user: User) -> None:
# or
class Priority(Enum):
    NORMAL = "normal"
    URGENT = "urgent"
def send(user: User, priority: Priority = Priority.NORMAL) -> None:
```

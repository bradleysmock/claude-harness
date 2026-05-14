# Rust — Code Generation Rules

Specific shapes the model must not write in Rust. Applies on top of the universal principles in `CLAUDE.md`.

## Panics

- Never `.unwrap()` or `.expect("msg")` in production code paths without justification. Return `Result` and let the caller decide. In tests, `.unwrap()` is fine.
- Never `panic!(` in library or request-path code. Panics are for genuinely unrecoverable invariant violations.

## Unsafe

- Never `unsafe { … }` without an immediately preceding comment block stating: (1) what invariant is upheld, (2) why the safe alternative is unsuitable.

## Subprocess & shell

- Never build a shell command with `format!` of user input. Use `std::process::Command::new("…").arg(…).arg(…)`.

## SQL

- Always parameterize. With sqlx/diesel, use the macro or builder API. Never `format!` user input into a SQL string.

## Error handling

- Never `let _ = result;` to discard a `Result` from a fallible call. If discarding is correct, name the reason: `let _ignored_for_<reason> = result;` and prefer `.ok()` with explicit handling.
- Avoid `?` at the top of a binary's `main` without a custom error type — propagate a clear context (`anyhow::Context`, `thiserror`, or a project error enum).

## Logging

- No `println!` / `eprintln!` in production code paths. Use `tracing` or `log`.

## Lint suppressions

- `#[allow(<lint>)] // <reason>`. Reason required. Never bare `#[allow(clippy::all)]` at module level.

# Go — Code Generation Rules

Specific shapes the model must not write in Go. Applies on top of the universal principles in `CLAUDE.md`.

## Subprocess & shell

- Never assemble a shell command by string-joining user input into `exec.Command("sh", "-c", concatenated)`. Pass arguments to `exec.Command` as a list.
  - Wrong: `exec.Command("sh", "-c", fmt.Sprintf("grep %s %s", pattern, path))`
  - Right: `exec.Command("grep", pattern, path)`

## Error handling

- Never `_ = err` to discard an error from a fallible call. If discarding is correct, name the reason inline.
- Never `if err != nil { return nil }` that drops the error without wrapping. Wrap with `fmt.Errorf("…: %w", err)` so context propagates.
- Never `panic(` in library or request-path code. `panic` is for genuinely unrecoverable invariant violations at startup.

## Goroutines & cancellation

- Never spawn a goroutine without a way to cancel or wait for it. Pass a `context.Context` and respect `ctx.Done()`.
- Never ignore `ctx.Err()` after a `select` that included `<-ctx.Done()`.

## SQL

- Always use parameterized queries. Never `fmt.Sprintf` user values into SQL.
- Wrong: `db.Query(fmt.Sprintf("SELECT * FROM users WHERE id = %d", id))`
- Right: `db.Query("SELECT * FROM users WHERE id = $1", id)`

## Logging

- No `fmt.Println` in production code paths. Use the project's logger (zap, slog, logrus).

## Lint suppressions

- `//nolint:<linter> // <reason>`. Reason required on the same line. Never bare `//nolint`.

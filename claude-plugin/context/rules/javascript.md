# JavaScript — Code Generation Rules

Specific shapes the model must not write in JavaScript. Applies on top of the universal principles in `CLAUDE.md`. TypeScript projects also load `.claude/rules/typescript.md` for additional rules.

## Code execution

- Never `eval(`, `new Function(string)`, or `setTimeout`/`setInterval` with a string argument. Pass functions, not strings.
- Never `vm.runInNewContext(userInput)` or equivalent.

## Subprocess & shell

- Never `child_process.exec(commandString)` or `execSync` with concatenated user input. Use `execFile` / `spawn` with argument arrays.
  - Wrong: `exec(\`grep ${pattern} ${path}\`)`
  - Right: `execFile("grep", [pattern, path])`

## DOM & rendering

- Never assign user-controlled values to `.innerHTML`, `.outerHTML`, or `document.write`. Use `.textContent`, or sanitize with a vetted library (DOMPurify) and document the sanitizer used.
- Never `dangerouslySetInnerHTML` (React) without a sanitizer + same-line comment naming it.

## URL & redirect

- Never `window.location = userValue` or build redirect URLs from user input without same-origin / allow-list enforcement.

## Promise & error handling

- Never an empty `.catch(() => {})` that swallows. Log with full context, propagate, or surface to the user.
- Never `await` inside a loop when work is independent — use `Promise.all` (be deliberate about `allSettled` vs `all` failure semantics).
- Never silently ignore unhandled rejections — the entry point must attach a handler.

## SQL & query builders

- Always parameterize. Never template-literal user values into SQL.
  - Wrong: `db.query(\`SELECT * FROM users WHERE id = ${id}\`)`
  - Right: `db.query("SELECT * FROM users WHERE id = $1", [id])`

## Logging

- No `console.log` in production code paths. Use the project's logger (pino, winston, etc.). `console.error` for genuinely unrecoverable startup errors is allowed.

## Lint suppressions

- `// eslint-disable-next-line <rule> — <reason>`. Reason on the same line. Never bare `eslint-disable`.

# Python — Code Generation Rules

Specific shapes the model must not write in Python. Applies on top of the universal principles in `CLAUDE.md`.

## Subprocess & shell

- Never `subprocess.run(..., shell=True)` or `Popen(..., shell=True)`. Pass argument lists.
  - Wrong: `subprocess.run(f"grep {pattern} {path}", shell=True)`
  - Right: `subprocess.run(["grep", pattern, path], check=True)`
  - Justified exception: `subprocess.run(cmd, shell=True)  # nosec: <specific reason>`

## Code execution & deserialization

- Never `eval(`, `exec(`, or `pickle.loads(` on a value you did not author. Use `ast.literal_eval` for literals, `json.loads` for JSON, or an explicit parser.

## Exception handling

- Never bare `except:`. Never `except Exception:` that swallows. Catch the specific type; if you must catch broadly at a boundary, `logger.exception(...)` and re-raise.
- Never `except asyncio.CancelledError:` without re-raising. Cancellation must propagate.

## Filesystem paths

- Never accept a user-supplied path component into `os.path.join` or `open` without containment. Use:
  ```python
  target = (allowed_root / user_path).resolve()
  target.relative_to(allowed_root)  # raises if escaped
  ```

## Defaults & assertions

- Never use a mutable default argument. Default to `None` and instantiate inside.
  - Wrong: `def f(items=[]):`
  - Right: `def f(items=None): items = list(items) if items is not None else []`
- Never `assert` for runtime validation in code that may run with `python -O`. Raise explicitly.

## SQL

- Always parameterize. Use the driver's binding (`?` for sqlite, `%s` for psycopg, `:name` for SQLAlchemy).
- Wrong: `cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")`
- Right: `cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`

## Logging

- No `print(` in non-CLI modules. Use the project's logger (typically `logging.getLogger(__name__)`).

## Type & lint suppressions

- `# type: ignore[<code>] — <reason>` and `# noqa: <code> — <reason>`. Reason on the same line.

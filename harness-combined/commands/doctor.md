Diagnose whether this project is ready to gate — a read-only, per-language check
of which gate tools are installed and on PATH.

Call the harness MCP tool `doctor(project_root)`. It scans the project root for
language manifests (`pyproject.toml` / `setup.py` / `setup.cfg` → Python,
`package.json` → TypeScript, `Cargo.toml` → Rust, `go.mod` → Go), then probes
each detected language's required gate tools by running `<tool> --version` under
a 5-second timeout. It never modifies the project or installs anything.

## Arguments

- **`project_root`** *(optional)* — the directory to inspect. Defaults to the
  current working directory when omitted or blank. An explicit value overrides
  the CWD, so you can point `/doctor` at another checkout. A path that is not a
  real directory (or one outside the allowed root) returns an error before any
  tool is probed.

## Output

The tool returns JSON `{"output": str, "any_missing": bool}`:

- **`output`** — a human-readable table per detected language. Each row is a
  tool name, its status token, and either the captured version string or an
  install hint:
  - `found` — on PATH, `--version` exited 0; the version is shown.
  - `found (error)` — on PATH but `--version` exited non-zero (installed, not
    healthy).
  - `missing` — not on PATH; an install hint (e.g. `pip install ruff`,
    `npm install -g typescript`) is shown.
  - `timeout` — the probe exceeded the 5-second limit.

  When no recognized manifest is found, `output` is
  `no supported languages detected`.

- **`any_missing`** — `true` when any required tool is `missing` or `timeout`,
  otherwise `false`. This is the machine-readable signal to relay to the
  operator: a `true` value means `/build` would fail for lack of tooling, so it
  is suitable for a CI preflight (surface it as a non-zero status).

## Reporting

Print the `output` table to the operator verbatim. When `any_missing` is `true`,
call it out explicitly and list the hinted installs; when `false`, confirm the
environment is ready to gate.

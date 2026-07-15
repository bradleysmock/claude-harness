/**
 * Shared config: locate the original harness-combined plugin tree and expose
 * the environment the Python hooks / MCP server expect.
 *
 * The Claude Code plugin injected `${CLAUDE_PLUGIN_ROOT}` into every hook
 * command, the MCP launcher, and 75+ markdown references. Pi does not inject
 * it, so we resolve the root once and set it on the environment of every
 * subprocess we spawn (hooks + MCP server). The prompt-template conversion
 * script (scripts/convert-commands.mjs) rewrites the in-prompt references to a
 * literal path so the model never needs the variable itself.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** Resolve the harness-combined root, honoring an explicit override first. */
export function harnessRoot(): string {
	const override = process.env.HARNESS_COMBINED_ROOT;
	if (override && fs.existsSync(override)) return override;

	// Default: sibling checkout next to this package (../../harness-combined).
	const sibling = path.resolve(HERE, "..", "..", "harness-combined");
	if (fs.existsSync(sibling)) return sibling;

	throw new Error(
		"harness-pi: cannot locate harness-combined. Set HARNESS_COMBINED_ROOT to its path.",
	);
}

/** Environment for every hook / server subprocess: injects the plugin-root token. */
export function harnessEnv(): NodeJS.ProcessEnv {
	return { ...process.env, CLAUDE_PLUGIN_ROOT: harnessRoot() };
}

/** Absolute path to the harness's vendored Python, falling back to python3. */
export function harnessPython(): string {
	const venvPy = path.join(harnessRoot(), ".venv", "bin", "python");
	return fs.existsSync(venvPy) ? venvPy : "python3";
}

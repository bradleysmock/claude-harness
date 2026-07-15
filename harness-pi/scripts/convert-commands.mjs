#!/usr/bin/env node
/**
 * Convert harness-combined/commands/*.md (Claude Code slash commands) into pi
 * prompt templates under harness-pi/prompts/.
 *
 * Two transforms:
 *   1. `${CLAUDE_PLUGIN_ROOT}` -> the absolute harness-combined path. Required:
 *      pi does not inject that variable, AND pi's template engine treats `${...}`
 *      as its own argument syntax, so the token must be resolved at convert time.
 *   2. Ensure a `description` frontmatter (pi falls back to the first line, but
 *      the CC command bodies open with instructions, so we synthesize one).
 *
 * `$ARGUMENTS` / `$1` etc. are left as-is — pi supports them natively.
 *
 * Usage: node scripts/convert-commands.mjs [path-to-harness-combined]
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root =
	process.argv[2] ||
	process.env.HARNESS_COMBINED_ROOT ||
	path.resolve(here, "..", "..", "harness-combined");

const srcDir = path.join(root, "commands");
const outDir = path.resolve(here, "..", "prompts");

if (!fs.existsSync(srcDir)) {
	console.error(`No commands dir at ${srcDir}`);
	process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });

let count = 0;
for (const file of fs.readdirSync(srcDir)) {
	if (!file.endsWith(".md")) continue;
	let body = fs.readFileSync(path.join(srcDir, file), "utf-8");

	// 1. Resolve the plugin-root token to a literal path.
	body = body.replaceAll("${CLAUDE_PLUGIN_ROOT}", root);

	// 2. Prepend a description frontmatter if none exists.
	if (!body.startsWith("---")) {
		const firstLine = body.split("\n").find((l) => l.trim()) ?? file;
		const desc = firstLine.replace(/[`*]/g, "").slice(0, 90).trim();
		body = `---\ndescription: ${desc}\n---\n${body}`;
	}

	fs.writeFileSync(path.join(outDir, file), body);
	count++;
}

console.error(`Converted ${count} commands -> ${outDir}`);

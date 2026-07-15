/**
 * MCP bridge extension.
 *
 * Launches the harness MCP server (bin/harness-server) on first use and
 * registers each of its 12 tools (gate_run, gate_run_on_dir, commit_lint,
 * spec_load, context_fetch, artifact, repair_run, memory, dag_load,
 * checkpoint, harness_status, doctor) as native Pi tools. The MCP tool's
 * JSON Schema is passed through verbatim as the Pi tool's parameter schema,
 * so the model calls them exactly as the original commands/flows expect.
 *
 * The server is started lazily on session_start and torn down on
 * session_shutdown, per the pi guidance on long-lived resources.
 */

import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { harnessEnv, harnessRoot } from "./harness-config.ts";
import { McpStdioClient } from "./mcp-client.ts";

export default function (pi: ExtensionAPI) {
	let client: McpStdioClient | null = null;
	let startPromise: Promise<void> | null = null;

	async function ensureStarted(cwd: string): Promise<McpStdioClient> {
		if (client) return client;
		if (!startPromise) {
			const root = harnessRoot();
			const launcher = path.join(root, "bin", "harness-server");
			const c = new McpStdioClient("bash", [launcher], harnessEnv(), cwd);
			startPromise = c.start().then(async () => {
				client = c;
				await registerTools(c);
			});
		}
		await startPromise;
		return client!;
	}

	async function registerTools(c: McpStdioClient): Promise<void> {
		const tools = await c.listTools();
		for (const tool of tools) {
			pi.registerTool({
				name: tool.name,
				label: tool.name,
				description: tool.description ?? `harness MCP tool: ${tool.name}`,
				// Pass the MCP JSON Schema straight through as the parameter schema.
				parameters: tool.inputSchema as never,
				async execute(_id, params) {
					const text = await c.callTool(tool.name, params as Record<string, unknown>);
					return { content: [{ type: "text", text }], details: {} };
				},
			});
		}
	}

	// Start eagerly so the tools appear in the startup header and are callable
	// without a warm-up round-trip. Failure is surfaced but non-fatal.
	pi.on("session_start", async (_event, ctx) => {
		try {
			await ensureStarted(ctx.cwd);
		} catch (err) {
			ctx.ui.notify(`harness MCP bridge failed to start: ${(err as Error).message}`, "error");
		}
	});

	pi.on("session_shutdown", async () => {
		client?.stop();
		client = null;
		startPromise = null;
	});
}

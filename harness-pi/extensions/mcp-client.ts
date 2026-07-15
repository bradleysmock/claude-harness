/**
 * Minimal MCP stdio client (JSON-RPC 2.0, newline-delimited).
 *
 * Enough of the protocol to launch the harness MCP server (bin/harness-server),
 * initialize, list tools, and call them. Pi ships with no MCP support by design
 * (see the pi README "No MCP"), so this is the bridge that lets the harness's
 * FastMCP server (server.py) be reused unmodified.
 *
 * Framing note: MCP stdio uses LF-delimited JSON objects, one per line — not
 * LSP Content-Length framing. stdout is the protocol channel; the server routes
 * all diagnostics to stderr.
 */

import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";

export interface McpToolDef {
	name: string;
	description?: string;
	inputSchema: Record<string, unknown>;
}

interface Pending {
	resolve: (value: unknown) => void;
	reject: (err: Error) => void;
}

export class McpStdioClient {
	private proc: ChildProcessWithoutNullStreams | null = null;
	private nextId = 1;
	private pending = new Map<number, Pending>();
	private buffer = "";

	constructor(
		private readonly command: string,
		private readonly args: string[],
		private readonly env: NodeJS.ProcessEnv,
		private readonly cwd: string,
	) {}

	async start(): Promise<void> {
		this.proc = spawn(this.command, this.args, {
			env: this.env,
			cwd: this.cwd,
			stdio: ["pipe", "pipe", "pipe"],
		});

		this.proc.stdout.setEncoding("utf-8");
		this.proc.stdout.on("data", (chunk: string) => this.onData(chunk));
		this.proc.stderr.on("data", () => {
			/* server diagnostics — swallow to keep the TUI clean */
		});
		this.proc.on("exit", (code) => {
			const err = new Error(`harness MCP server exited (code ${code})`);
			for (const p of this.pending.values()) p.reject(err);
			this.pending.clear();
		});

		await this.request("initialize", {
			protocolVersion: "2024-11-05",
			capabilities: {},
			clientInfo: { name: "harness-pi", version: "0.1.0" },
		});
		this.notify("notifications/initialized", {});
	}

	async listTools(): Promise<McpToolDef[]> {
		const res = (await this.request("tools/list", {})) as { tools: McpToolDef[] };
		return res.tools ?? [];
	}

	async callTool(name: string, args: Record<string, unknown>): Promise<string> {
		const res = (await this.request("tools/call", { name, arguments: args })) as {
			content?: Array<{ type: string; text?: string }>;
			isError?: boolean;
		};
		const text = (res.content ?? [])
			.filter((c) => c.type === "text")
			.map((c) => c.text ?? "")
			.join("\n");
		if (res.isError) throw new Error(text || `tool ${name} failed`);
		return text;
	}

	stop(): void {
		this.proc?.kill();
		this.proc = null;
	}

	private onData(chunk: string): void {
		this.buffer += chunk;
		let idx: number;
		// Strict LF framing — never use a generic line reader here.
		while ((idx = this.buffer.indexOf("\n")) !== -1) {
			const line = this.buffer.slice(0, idx).trim();
			this.buffer = this.buffer.slice(idx + 1);
			if (!line) continue;
			this.handleMessage(line);
		}
	}

	private handleMessage(line: string): void {
		let msg: { id?: number; result?: unknown; error?: { message?: string } };
		try {
			msg = JSON.parse(line);
		} catch {
			return; // ignore non-JSON noise
		}
		if (typeof msg.id !== "number") return; // notification / request from server
		const pending = this.pending.get(msg.id);
		if (!pending) return;
		this.pending.delete(msg.id);
		if (msg.error) pending.reject(new Error(msg.error.message ?? "MCP error"));
		else pending.resolve(msg.result);
	}

	private request(method: string, params: unknown): Promise<unknown> {
		if (!this.proc) return Promise.reject(new Error("MCP server not started"));
		const id = this.nextId++;
		const payload = `${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`;
		return new Promise((resolve, reject) => {
			this.pending.set(id, { resolve, reject });
			this.proc!.stdin.write(payload);
		});
	}

	private notify(method: string, params: unknown): void {
		if (!this.proc) return;
		this.proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`);
	}
}

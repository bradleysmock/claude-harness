/**
 * Subagent extension.
 *
 * Pi has no sub-agents by design. The harness flows spawn a `critic` subagent
 * (build-ticket.md Step 7, problem.md, replan.md) and a `requirements-analyst`.
 * This registers a `task` tool that:
 *   1. discovers agents from harness-combined/agents/*.md (frontmatter:
 *      name, description, tools),
 *   2. spawns an isolated `pi -p` process with a restricted toolset and the
 *      agent body as its system prompt, and
 *   3. returns only the final report — the parent never sees the sub-run's
 *      reasoning (matching the CC subagent contract in critic.md).
 *
 * CC tool names in agent frontmatter are mapped to pi's built-ins:
 *   Read->read  Grep->grep  Glob->find  Write->write  Edit->edit  Bash->bash
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { type ExtensionAPI, parseFrontmatter } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { harnessEnv, harnessRoot } from "./harness-config.ts";

interface AgentConfig {
	name: string;
	description: string;
	tools?: string[];
	systemPrompt: string;
}

const CC_TO_PI_TOOL: Record<string, string> = {
	Read: "read",
	Grep: "grep",
	Glob: "find",
	Write: "write",
	Edit: "edit",
	MultiEdit: "edit",
	Bash: "bash",
	LS: "ls",
};

function discoverAgents(): Map<string, AgentConfig> {
	const dir = path.join(harnessRoot(), "agents");
	const map = new Map<string, AgentConfig>();
	if (!fs.existsSync(dir)) return map;
	for (const entry of fs.readdirSync(dir)) {
		if (!entry.endsWith(".md")) continue;
		const raw = fs.readFileSync(path.join(dir, entry), "utf-8");
		const { frontmatter, body } = parseFrontmatter<Record<string, string>>(raw);
		if (!frontmatter.name || !frontmatter.description) continue;
		const tools = frontmatter.tools
			?.split(",")
			.map((t) => CC_TO_PI_TOOL[t.trim()] ?? t.trim().toLowerCase())
			.filter(Boolean);
		map.set(frontmatter.name, {
			name: frontmatter.name,
			description: frontmatter.description,
			tools: tools && tools.length ? tools : undefined,
			systemPrompt: body,
		});
	}
	return map;
}

function runSubagent(agent: AgentConfig, task: string, cwd: string): Promise<string> {
	const args = ["-p", "--no-session", "--append-system-prompt", agent.systemPrompt];
	if (agent.tools) args.push("--tools", agent.tools.join(","));
	args.push(task);

	return new Promise((resolve, reject) => {
		// CLAUDE_PLUGIN_ROOT is injected so the agent body's path references resolve.
		const proc = spawn("pi", args, { env: harnessEnv(), cwd });
		let out = "";
		let err = "";
		proc.stdout.on("data", (d) => (out += d));
		proc.stderr.on("data", (d) => (err += d));
		proc.on("error", reject);
		proc.on("close", (code) => {
			if (code === 0) resolve(out.trim());
			else reject(new Error(err.trim() || `subagent exited ${code}`));
		});
	});
}

export default function (pi: ExtensionAPI) {
	const agents = discoverAgents();
	if (agents.size === 0) return;
	const names = Array.from(agents.keys());

	pi.registerTool({
		name: "task",
		label: "Subagent",
		description: `Delegate a task to a specialized read/write-scoped subagent. Available agents: ${names
			.map((n) => `${n} (${agents.get(n)!.description})`)
			.join("; ")}`,
		promptSnippet: "Delegate to a subagent (e.g. critic) via task",
		parameters: Type.Object({
			agent: StringEnum(names as [string, ...string[]]),
			task: Type.String({ description: "The full task/prompt for the subagent" }),
		}),
		async execute(_id, params, _signal, _onUpdate, ctx) {
			const agent = agents.get(params.agent);
			if (!agent) {
				return { content: [{ type: "text", text: `Unknown agent: ${params.agent}` }], isError: true };
			}
			try {
				const report = await runSubagent(agent, params.task, ctx.cwd);
				return { content: [{ type: "text", text: report }], details: { agent: params.agent } };
			} catch (e) {
				return { content: [{ type: "text", text: `Subagent failed: ${(e as Error).message}` }], isError: true };
			}
		},
	});
}

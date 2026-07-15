/**
 * Hook bridge extension.
 *
 * The Claude Code plugin wired five Python hooks through the CC hook system
 * (PreToolUse / PostToolUse / Stop with a Write|Edit|MultiEdit matcher). Pi has
 * no hook system; it has extension events. This bridge maps them:
 *
 *   CC PreToolUse  (Write|Edit|MultiEdit) -> pi tool_call     (can block)
 *   CC PostToolUse (Write|Edit|MultiEdit) -> pi tool_result
 *   CC Stop                                -> pi agent_settled
 *
 * Two schema gaps are handled here:
 *   1. Tool names: pi uses `write` / `edit` (lowercase, no MultiEdit). The
 *      hooks match CC's `Write` / `Edit` / `MultiEdit` and read CC's
 *      tool_input keys (file_path, content, new_string, edits[].new_string).
 *   2. Blocking: CC hooks signal a block with exit code 2 + a stderr message.
 *      Pi blocks a tool_call by returning { block: true, reason }.
 */

import { spawn } from "node:child_process";
import * as path from "node:path";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { harnessEnv, harnessPython, harnessRoot } from "./harness-config.ts";

interface HookResult {
	code: number;
	stderr: string;
	stdout: string;
}

/** Run a hook script, feeding it a CC-shaped JSON payload on stdin. */
function runHook(script: string, payload: unknown, cwd: string): Promise<HookResult> {
	const scriptPath = path.join(harnessRoot(), "hooks", script);
	return new Promise((resolve) => {
		const proc = spawn(harnessPython(), [scriptPath], { env: harnessEnv(), cwd });
		let stderr = "";
		let stdout = "";
		proc.stderr.on("data", (d) => (stderr += d));
		proc.stdout.on("data", (d) => (stdout += d));
		proc.on("error", (err) => resolve({ code: 0, stderr: String(err), stdout: "" }));
		proc.on("close", (code) => resolve({ code: code ?? 0, stderr, stdout }));
		proc.stdin.write(JSON.stringify(payload));
		proc.stdin.end();
	});
}

/**
 * Translate a pi write/edit tool call into the CC PreToolUse payload the hooks
 * parse. pi `edit` (multiple oldText/newText pairs) maps to CC `MultiEdit`.
 */
function toCcPayload(
	toolName: string,
	input: Record<string, unknown>,
): { tool_name: string; tool_input: Record<string, unknown> } | null {
	if (toolName === "write") {
		return {
			tool_name: "Write",
			tool_input: { file_path: input.path, content: input.content ?? "" },
		};
	}
	if (toolName === "edit") {
		const edits = Array.isArray(input.edits) ? input.edits : [];
		const ccEdits = edits.map((e: any) => ({
			old_string: e.oldText ?? "",
			new_string: e.newText ?? "",
		}));
		// Single-edit calls map to CC Edit; multi-edit calls to MultiEdit.
		if (ccEdits.length === 1) {
			return {
				tool_name: "Edit",
				tool_input: {
					file_path: input.path,
					old_string: ccEdits[0].old_string,
					new_string: ccEdits[0].new_string,
				},
			};
		}
		return {
			tool_name: "MultiEdit",
			tool_input: { file_path: input.path, edits: ccEdits },
		};
	}
	return null;
}

// Cap how many times a failing Stop gate may force another turn, so a gate
// the model cannot satisfy does not loop forever.
const MAX_STOP_ENFORCEMENTS = 3;

export default function (pi: ExtensionAPI) {
	let stopEnforcements = 0;

	// ── PreToolUse: pre_ticket_diff + pre_write_guard (blocking) ──────────────
	pi.on("tool_call", async (event, ctx) => {
		if (!isToolCallEventType("write", event) && !isToolCallEventType("edit", event)) return;
		const payload = toCcPayload(event.toolName, event.input as Record<string, unknown>);
		if (!payload) return;

		for (const script of ["pre_ticket_diff.py", "pre_write_guard.py"]) {
			const res = await runHook(script, payload, ctx.cwd);
			if (res.code === 2) {
				return { block: true, reason: res.stderr.trim() || `${script} blocked the write` };
			}
		}
	});

	// ── PostToolUse: post_write_gate ──────────────────────────────────────────
	pi.on("tool_result", async (event, ctx) => {
		if (event.toolName !== "write" && event.toolName !== "edit") return;
		if (event.isError) return; // only gate successful writes
		const payload = toCcPayload(event.toolName, event.input as Record<string, unknown>);
		if (!payload) return;
		await runHook("post_write_gate.py", payload, ctx.cwd);
	});

	// ── Stop: stop_full_gate + ticket_commit_guard ────────────────────────────
	// agent_settled fires once Pi will not continue automatically — the closest
	// analogue to CC's Stop event.
	pi.on("agent_settled", async (_event, ctx) => {
		const stopPayload = { hook_event_name: "Stop", cwd: ctx.cwd };
		const failures: string[] = [];
		for (const script of ["stop_full_gate.py", "ticket_commit_guard.py"]) {
			const res = await runHook(script, stopPayload, ctx.cwd);
			// CC Stop hooks surface feedback to the model via stderr on exit 2.
			if (res.code === 2 && res.stderr.trim()) {
				failures.push(`[${script}]\n${res.stderr.trim()}`);
			}
		}

		if (failures.length === 0) {
			stopEnforcements = 0; // clean settle — reset the loop guard
			return;
		}

		// Print mode (-p) is one-shot: it tears down as soon as the prompt is
		// answered, so a queued follow-up would race the shutdown (stale ctx).
		// Re-prompting is meaningful only in interactive/RPC sessions; elsewhere
		// just surface the failure.
		if (ctx.mode === "print" || ctx.mode === "json") {
			ctx.ui.notify(`harness Stop gate failed:\n${failures.join("\n\n")}`, "warn");
			return;
		}

		// Enforcement: CC re-prompts on a failing Stop hook. Pi's turn has already
		// settled, so re-open it by injecting the gate feedback as a follow-up
		// user message — but only up to MAX_STOP_ENFORCEMENTS times.
		if (stopEnforcements >= MAX_STOP_ENFORCEMENTS) {
			ctx.ui.notify(
				`harness gates still failing after ${MAX_STOP_ENFORCEMENTS} attempts — stopping enforcement:\n${failures.join("\n\n")}`,
				"error",
			);
			stopEnforcements = 0;
			return;
		}

		stopEnforcements++;
		const body = failures.join("\n\n");
		ctx.ui.notify(`harness Stop gate failed (attempt ${stopEnforcements}) — re-prompting`, "warn");
		pi.sendUserMessage(
			`The harness Stop gates failed and must be resolved before finishing. ` +
				`Fix the underlying issues, then continue.\n\n${body}`,
			{ deliverAs: "followUp" },
		);
	});
}

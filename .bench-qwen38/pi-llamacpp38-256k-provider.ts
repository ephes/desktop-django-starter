import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Qwen3.8-27B dense (Q4_K_M, ggml-org) on llama.cpp at its FULL trained context
// (262144 / 256k), mirroring .bench-qwen36/pi-llamacpp-256k-provider.ts so the
// one-shot wrap result is comparable to the 2026-06 Qwen3.6 256k cells.
// Pair with a llama-server started with `-c 262144 --alias qwen3.8-27b`.
// maxTokens stays at 16384: an 8192 output cap truncated thinking traces
// mid-stage in the earlier campaign and is the suspected cause of a derail.

export default function (pi: ExtensionAPI) {
	pi.registerProvider("llamacpp38", {
		name: "llama.cpp Qwen3.8 (256k ctx)",
		baseUrl: "http://127.0.0.1:18084/v1",
		api: "openai-completions",
		apiKey: "llamacpp-local",
		compat: {
			supportsStore: false,
			supportsDeveloperRole: false,
			supportsReasoningEffort: true,
			supportsUsageInStreaming: true,
			maxTokensField: "max_tokens",
			supportsStrictMode: false,
			thinkingFormat: "qwen-chat-template",
		},
		models: [
			{
				id: "qwen3.8-27b",
				name: "Qwen3.8-27B (llama.cpp, 256k ctx)",
				reasoning: true,
				input: ["text"],
				contextWindow: 262144,
				maxTokens: 16384,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				compat: {
					supportsDeveloperRole: false,
					supportsReasoningEffort: true,
					reasoningEffortMap: { minimal: "low", low: "low", medium: "medium", high: "high", xhigh: "high" },
					thinkingFormat: "qwen-chat-template",
					maxTokensField: "max_tokens",
					supportsStrictMode: false,
				},
			},
		],
	} as any);
}

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Laguna XS 2.1 (33B total / ~3B active MoE, poolside official Q4_K_M GGUF)
// on llama.cpp at the model's full trained context (262144), mirroring
// .bench-qwen38/pi-llamacpp38-256k-provider.ts so the one-shot wrap result is
// comparable to the Qwen3.8 256k cells.
// Laguna's chat template exposes a binary enable_thinking toggle (default
// false) and no reasoning_effort levels, so thinking lanes are selected
// server-side via `--chat-template-kwargs '{"enable_thinking":...}'` and
// supportsReasoningEffort is false here.
// Pair with a llama-server started with `-c 262144 --alias laguna-xs-2.1`
// on port 18088.

export default function (pi: ExtensionAPI) {
	pi.registerProvider("llamacpplaguna", {
		name: "llama.cpp Laguna XS 2.1 (256k ctx)",
		baseUrl: "http://127.0.0.1:18088/v1",
		api: "openai-completions",
		apiKey: "llamacpp-local",
		compat: {
			supportsStore: false,
			supportsDeveloperRole: false,
			supportsReasoningEffort: false,
			supportsUsageInStreaming: true,
			maxTokensField: "max_tokens",
			supportsStrictMode: false,
			thinkingFormat: "chat-template",
		},
		models: [
			{
				id: "laguna-xs-2.1",
				name: "Laguna XS 2.1 (llama.cpp, 256k ctx)",
				reasoning: true,
				input: ["text"],
				contextWindow: 262144,
				maxTokens: 16384,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				compat: {
					supportsDeveloperRole: false,
					supportsReasoningEffort: false,
					thinkingFormat: "chat-template",
					maxTokensField: "max_tokens",
					supportsStrictMode: false,
				},
			},
		],
	} as any);
}

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Experiment provider: qwen 3.6 27b on llama.cpp at its FULL trained context
// (262144 / 256k), not the 32k the earlier one-shot run used. Pair with a
// llama-server started with `-c 262144`. Lets pi use the whole window so the
// one-shot context-window question is tested fairly (parallel to the ds4 256k run).

export default function (pi: ExtensionAPI) {
	pi.registerProvider("llamacpp256k", {
		name: "llama.cpp (256k ctx)",
		baseUrl: "http://127.0.0.1:8080/v1",
		api: "openai-completions",
		apiKey: "llamacpp-local",
		compat: {
			supportsStore: false,
			supportsDeveloperRole: false,
			supportsReasoningEffort: false,
			supportsUsageInStreaming: true,
			maxTokensField: "max_tokens",
			supportsStrictMode: false,
		},
		models: [
			{
				id: "qwen3.6-27b",
				name: "Qwen3.6-27B (llama.cpp, 256k ctx)",
				reasoning: false,
				input: ["text"],
				contextWindow: 262144,
				maxTokens: 16384,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			},
		],
	} as any);
}

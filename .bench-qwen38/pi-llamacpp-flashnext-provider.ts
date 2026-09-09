import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Qwen3.8-Flash-Next (UD-IQ4_XS, unsloth) on the source-built llama.cpp that
// carries the qwen4exp arch (PR #27742 + #27880). Served on :18085 with
// -ot "ple_ngram_embd=CPU" to keep the ~51B n-gram embedding table out of the
// GPU/wired allocation. Context is 131072, not the 262144 used for the 27B
// cells — a deliberate deviation to keep memory headroom on a 128 GB host.

export default function (pi: ExtensionAPI) {
	pi.registerProvider("llamacppfn", {
		name: "llama.cpp Qwen3.8-Flash-Next",
		baseUrl: "http://127.0.0.1:18085/v1",
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
				id: "qwen3.8-flash-next",
				name: "Qwen3.8-Flash-Next (llama.cpp, 128k ctx)",
				reasoning: true,
				input: ["text"],
				contextWindow: 131072,
				maxTokens: 16384,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				compat: {
					supportsDeveloperRole: false,
					supportsReasoningEffort: true,
					reasoningEffortMap: { minimal: "low", low: "low", medium: "medium", high: "xhigh", xhigh: "xhigh" },
					thinkingFormat: "qwen-chat-template",
					maxTokensField: "max_tokens",
					supportsStrictMode: false,
				},
			},
		],
	} as any);
}

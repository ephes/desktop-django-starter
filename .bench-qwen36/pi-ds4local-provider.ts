import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Registers a pi provider for a MANUALLY-started ds4.c server (DeepSeek V4 Flash)
// on an alternate port, so the staged django-resume wrap can be benchmarked
// against ds4 without disturbing the user's installed pi-sd4-provider extension
// (which hardwires port 8000). Start the server yourself, e.g.:
//   ds4-server -m ds4flash.gguf --host 127.0.0.1 --port 8002 -c 32768
//
// Compat settings mirror the installed pi-sd4-provider so multi-turn tool calling
// works (ds4 requires reasoning_content on assistant messages).

const PROVIDER_ID = "ds4local";
const BASE_URL = "http://127.0.0.1:8002/v1";

export default function (pi: ExtensionAPI) {
	pi.registerProvider(PROVIDER_ID, {
		name: "ds4.c local (alt port)",
		baseUrl: BASE_URL,
		api: "openai-completions",
		apiKey: "dsv4-local",
		compat: {
			supportsStore: false,
			supportsDeveloperRole: false,
			supportsReasoningEffort: true,
			supportsUsageInStreaming: true,
			maxTokensField: "max_tokens",
			supportsStrictMode: false,
			thinkingFormat: "deepseek",
			requiresReasoningContentOnAssistantMessages: true,
		},
		models: [
			{
				id: "deepseek-v4-flash",
				name: "DeepSeek V4 Flash (ds4.c local)",
				reasoning: true,
				thinkingLevelMap: {
					minimal: "low",
					low: "low",
					medium: "medium",
					high: "high",
					xhigh: "xhigh",
				},
				input: ["text"],
				contextWindow: 100000,
				maxTokens: 384000,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			},
		],
	} as any);
}

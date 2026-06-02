import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Minimal pi provider that targets a local Ollama server through its
// OpenAI-compatible endpoint. Used to drive local GGUF models (e.g. the
// qwen 3.6 27b benchmark target) as a tool-using agent inside pi.

const PROVIDER_ID = "ollama";
const BASE_URL = process.env.OLLAMA_HOST
	? `http://${process.env.OLLAMA_HOST.replace(/^https?:\/\//, "")}/v1`
	: "http://127.0.0.1:11434/v1";

const MODELS = [
	{
		id: "qwen36-27b-tools",
		name: "Qwen 3.6 27B tools (Ollama q4km)",
		contextWindow: 32768,
		maxTokens: 8192,
	},
	{
		id: "qwen36-27b-gguf:q4km",
		name: "Qwen 3.6 27B (Ollama q4km)",
		contextWindow: 65536,
		maxTokens: 16384,
	},
	{
		id: "qwen36-35b-a3b-gguf:q4km",
		name: "Qwen 3.6 35B A3B (Ollama q4km)",
		contextWindow: 65536,
		maxTokens: 16384,
	},
	{
		id: "qwen3-coder:30b-a3b-q4_K_M",
		name: "Qwen3 Coder 30B A3B (Ollama)",
		contextWindow: 65536,
		maxTokens: 16384,
	},
];

export default function (pi: ExtensionAPI) {
	pi.registerProvider(PROVIDER_ID, {
		name: "Ollama (local)",
		baseUrl: BASE_URL,
		api: "openai-completions",
		apiKey: "ollama-local",
		compat: {
			supportsStore: false,
			supportsDeveloperRole: false,
			supportsReasoningEffort: false,
			supportsUsageInStreaming: true,
			maxTokensField: "max_tokens",
			supportsStrictMode: false,
		},
		models: MODELS.map((m) => ({
			id: m.id,
			name: m.name,
			reasoning: false,
			input: ["text"],
			contextWindow: m.contextWindow,
			maxTokens: m.maxTokens,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		})),
	} as any);
}

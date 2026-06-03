import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Qwen3.6-35B-A3B (MoE, 3B active) on llama.cpp at its full 256k trained context.
// Pair with: llama-server -m Qwen3.6-35B-A3B-UD-Q4_K_M.gguf --jinja -c 262144 ... :8080
export default function (pi: ExtensionAPI) {
	pi.registerProvider("llamacppmoe", {
		name: "llama.cpp MoE (256k)",
		baseUrl: "http://127.0.0.1:8080/v1",
		api: "openai-completions",
		apiKey: "llamacpp-local",
		compat: { supportsStore: false, supportsDeveloperRole: false, supportsReasoningEffort: false, supportsUsageInStreaming: true, maxTokensField: "max_tokens", supportsStrictMode: false },
		models: [{ id: "qwen3.6-35b-a3b", name: "Qwen3.6-35B-A3B (llama.cpp, 256k)", reasoning: false, input: ["text"], contextWindow: 262144, maxTokens: 16384, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
	} as any);
}

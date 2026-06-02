import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Registers pi providers for local OpenAI-compatible model servers so the same
// Qwen3.6-27B weights can be driven through pi as a tool-using agent regardless
// of runtime. Used to compare llama.cpp and MLX against the Ollama baseline.
//
//   llama.cpp:  llama-server -m Qwen3.6-27B-Q4_K_M.gguf --jinja --port 8080
//   MLX:        mlx_lm.server --model mlx-community/Qwen3.6-27B-4bit --port 8081
//
// The request `model` string is ignored by single-model servers, so we expose a
// friendly id for each provider.

function register(pi: ExtensionAPI, id: string, name: string, port: number, modelId: string) {
	pi.registerProvider(id, {
		name,
		baseUrl: `http://127.0.0.1:${port}/v1`,
		api: "openai-completions",
		apiKey: `${id}-local`,
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
				id: modelId,
				name: `${name} Qwen3.6-27B`,
				reasoning: false,
				input: ["text"],
				contextWindow: 32768,
				maxTokens: 8192,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			},
		],
	} as any);
}

export default function (pi: ExtensionAPI) {
	register(pi, "llamacpp", "llama.cpp", 8080, "qwen3.6-27b");
	// mlx_lm.server honors the request's `model` field and resolves it as a HF
	// repo id, so it must match the loaded model exactly (not a friendly alias).
	register(pi, "mlx", "MLX", 8081, "mlx-community/Qwen3.6-27B-4bit");
}

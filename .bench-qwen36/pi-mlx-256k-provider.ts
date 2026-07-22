import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Experiment provider: qwen 3.6 27b on MLX at its FULL trained context
// (262144 / 256k) with a generous 16k output budget, parallel to
// pi-llamacpp-256k-provider.ts. The default pi-localserver-provider.ts MLX entry
// caps output at 8192 / 32k, which can truncate long thinking traces mid-stage
// (the suspected cause of the 2026-06-01 ds4 thinking=high Stage-3 derail on
// django-resume). This provider gives thinking mode the whole window.
//
//   MLX: mlx_lm.server --model mlx-community/Qwen3.6-27B-4bit --port 8081
//
// mlx_lm.server resolves the request `model` field as a HF repo id, so it must
// match the loaded model exactly (not a friendly alias).

export default function (pi: ExtensionAPI) {
	pi.registerProvider("mlx256k", {
		name: "MLX (256k ctx)",
		baseUrl: "http://127.0.0.1:8081/v1",
		api: "openai-completions",
		apiKey: "mlx-local",
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
				id: "mlx-community/Qwen3.6-27B-4bit",
				name: "Qwen3.6-27B (MLX, 256k ctx)",
				reasoning: false,
				input: ["text"],
				contextWindow: 262144,
				maxTokens: 16384,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			},
		],
	} as any);
}

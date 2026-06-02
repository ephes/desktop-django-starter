# How-to: local-model django-resume wrap demo

The canonical, rendered version of this runbook now lives in the Sphinx docs:

- Source: `docs/demo-local-model-wrap.md`
- Rendered: `docs/_build/html/demo-local-model-wrap.html` (build with `just docs-build`,
  open with `just docs`), linked from the docs index under **Guides**.

It covers, for Ollama / llama.cpp / MLX / ds4: prerequisites, starting each model
server, running the staged wrap (via `run-staged-wrap.sh` or the manual per-stage
Pi commands), the independent Pi judge, and per-model absolute timings.

The reproduction tooling it refers to is all in this directory:

- `pi-ollama-provider.ts`, `pi-localserver-provider.ts`, `pi-ds4local-provider.ts`
  — Pi provider extensions per runtime
- `Modelfile.qwen36-27b-tools` — tool-capable Ollama model build
- `run-staged-wrap.sh` — clean-clone + scaffold + Stage 2/3 + smoke runner
- `stage-2-filled.md`, `stage-3-filled.md`, `judge-prompt.md` — filled prompts
- `RUNTIME-COMPARISON.md`, `results-*/` — comparison table and per-run logs

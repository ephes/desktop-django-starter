# Final goal judge: did the django-cast benchmark reach its goal?

You are an independent **judge agent**. Verify with your bash/read tools; do not be
agreeable.

## The goal

"Tackle django-cast in the same way we did with django-resume and django-wiki: run the
same benchmarks and document." That means the same staged Electron-wrap matrix used for
django-wiki: 4 inference engines (Ollama, llama.cpp, MLX, ds4.c), two models (qwen 3.6
27b and DeepSeek V4 Flash), and thinking-mode variation (at least one model run both
off and high). Not complete until we have evidence for all cells. Each cell must drive
the staged Electron wrap of `django-cast` to a working packaged app (smoke serving
`/health/` 200 and the Wagtail root `/` 200) with no model source corruption
(verification-only zero-edit is an accepted pass).

## Evidence to audit

Per-cell results live under `/Users/jochen/projects/desktop-django-starter/.bench-qwen36/`:

- `results-cast-ollama/`             — engine: Ollama,    model: qwen 3.6 27b,      thinking: off
- `results-cast-llamacpp/`           — engine: llama.cpp, model: qwen 3.6 27b,      thinking: off
- `results-cast-mlx/`                — engine: MLX,       model: qwen 3.6 27b,      thinking: off
- `results-cast-llamacpp-thinkhigh/` — engine: llama.cpp, model: qwen 3.6 27b,      thinking: high
- `results-cast-ds4/`                — engine: ds4.c,     model: DeepSeek V4 Flash, thinking: off
- `results-cast-ds4-thinkhigh/`      — engine: ds4.c,     model: DeepSeek V4 Flash, thinking: high

For each directory, read `summary.txt` (check `app_served=1`, `health200>=1`,
`stage2_exit=0`, `stage3_exit=0`, `git_changed_files` small) and spot-check
`verify-smoke.log` (look for `GET /health/ ... 200` and `GET / ... 200`) and
`stage2.log` / `stage3.log` (coherent verification-only summaries, no drift/corruption).

A separate live judge already re-ran the packaged smoke on the final clone and
returned PASS (`/tmp/cast-judge.log`); you may read it.

## What to decide

1. Are all **4 engines** represented (Ollama, llama.cpp, MLX, ds4)?
2. Are **2 models** represented (qwen 3.6 27b and DeepSeek V4 Flash)?
3. Is **thinking-mode variation** present (at least one model run both off and high)?
4. Does **every** cell show a working wrap (`app_served=1`, smoke `/health/` 200 and
   `/` 200) with no source corruption?

## Verdict

End with:

```
GOAL_REACHED: YES   (or NO)
REASON: <2-3 sentences citing which cells you verified and any gaps>
```

Answer YES only if evidence exists for all 4 engines, both models, thinking-mode
variation, and every cell is a working, uncorrupted wrap.

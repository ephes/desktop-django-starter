# Final goal judge: did the django-wiki benchmark reach its goal?

You are an independent **judge agent**. Verify with your bash/read tools; do not be
agreeable.

## The goal

"Do the same benchmark for django-wiki as we did for django-resume: 4 inference
engines, two models, different thinking modes. Not complete until we have evidence for
all." Each cell must drive the staged Electron wrap of `django-wiki` to a working
packaged app (smoke serving `/health/` 200 and the wiki root `/` 200) with no model
source corruption (verification-only zero-edit is an accepted pass).

## Evidence to audit

Per-cell results live under `/Users/jochen/projects/desktop-django-starter/.bench-qwen36/`:

- `results-wiki-ollama/`            — engine: Ollama,   model: qwen 3.6 27b,        thinking: off
- `results-wiki-llamacpp/`          — engine: llama.cpp, model: qwen 3.6 27b,        thinking: off
- `results-wiki-mlx/`               — engine: MLX,       model: qwen 3.6 27b,        thinking: off
- `results-wiki-llamacpp-thinkhigh/`— engine: llama.cpp, model: qwen 3.6 27b,        thinking: high
- `results-wiki-ds4/`               — engine: ds4.c,     model: DeepSeek V4 Flash,   thinking: off
- `results-wiki-ds4-thinkhigh/`     — engine: ds4.c,     model: DeepSeek V4 Flash,   thinking: high

For each directory, read `summary.txt` (check `app_served=1`, `health200>=1`,
`stage2_exit=0`, `stage3_exit=0`, `git_changed_files` small) and spot-check
`verify-smoke.log` (look for `GET /health/ ... 200` and `GET / ... 200`) and
`stage2.log` / `stage3.log` (coherent verification-only summaries, no drift/corruption).

A separate live judge already re-ran the packaged smoke on the final clone and
returned PASS (`/tmp/wiki-judge-ds4high.log`); you may read it.

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

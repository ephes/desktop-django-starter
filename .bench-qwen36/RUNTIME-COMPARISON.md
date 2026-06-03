# Qwen 3.6 27B runtime comparison — staged django-resume Electron wrap

Date: 2026-06-02. Host: Apple Silicon (Mac16,9), arm64. Starter ref: `805f621`.

Same model family at ~4-bit, driven through `pi` as a tool-using agent over each
runtime's OpenAI-compatible `/v1/chat/completions` endpoint. Identical staged workflow
(deterministic Stage 1 scaffold, then qwen-run Stage 2 + Stage 3), identical runner
(`.bench-qwen36/run-staged-wrap.sh`), identical disposable target
(`django-resume-clean`).

## Weights / quant per runtime

| Runtime   | Weights                                            | Quant      | Tool calling |
|-----------|----------------------------------------------------|------------|--------------|
| Ollama    | `qwen36-27b-tools` (derived from `qwen36-27b-gguf:q4km`) | GGUF Q4_K_M | needed a derived Modelfile with the Qwen3 ChatML template (the imported GGUF shipped a bare `{{ .Prompt }}` template) |
| llama.cpp | `Qwen3.6-27B-Q4_K_M.gguf` (`llama-server --jinja`) | GGUF Q4_K_M | native — `--jinja` reads the GGUF's embedded Qwen3 chat template |
| MLX       | `mlx-community/Qwen3.6-27B-4bit` (`mlx_lm.server`) | MLX 4-bit  | native — emits OpenAI `tool_calls` (request `model` must be the exact HF repo id) |

## End-to-end staged-wrap wall-clock (includes tool execution: uv, npm, node tests, smoke)

| Runtime   | Stage 2 | Stage 3 | Stage 2+3 | packaged smoke         | model edits |
|-----------|---------|---------|-----------|------------------------|-------------|
| Ollama    | 73.7s   | 97.4s   | 171.1s    | /health/200 / 302 /resume/200 | 0 (verification-only) |
| llama.cpp | 41.7s   | 70.7s   | 112.4s    | /health/200 / 302 /resume/200 | 0 (verification-only) |
| MLX       | 40.0s   | 70.2s   | 110.2s    | /health/200 / 302 /resume/200 | 0 (verification-only) |

## Raw decode speed (250-word essay, max_tokens=300, temp=0, warmed)

| Runtime   | completion tokens | wall   | decode      |
|-----------|-------------------|--------|-------------|
| Ollama    | 300               | 18.73s | 16.0 tok/s  |
| llama.cpp | 300               | 13.35s | 22.5 tok/s  |
| MLX       | 300               | 11.15s | **26.9 tok/s** |

## Judge (pi / openai-codex/gpt-5.5, independent, re-ran smoke itself)

| Runtime   | Verdict |
|-----------|---------|
| Ollama    | PASS    |
| llama.cpp | PASS    |
| MLX       | PASS    |

## Takeaways

- All three runtimes drove qwen 3.6 27b to a working Electron-wrapped django-resume,
  judge-confirmed. The wrap is runtime-agnostic.
- MLX is fastest at decode (~1.7x Ollama), llama.cpp close behind (~1.4x Ollama). The
  end-to-end stage gap is smaller because each stage's wall-clock is dominated by fixed
  tool execution (uv venv resolve, npm, node tests, packaged smoke), not model decode.
- Ollama's slower decode here is partly its server defaults; the headline is that
  llama.cpp and MLX both serve the same ~4-bit weights noticeably faster, with native
  tool calling and no Modelfile surgery.
- Tool-calling gotchas: Ollama needed a real chat template re-attached; mlx_lm.server
  resolves the request `model` as a HF repo id so it must match exactly.

---

# Second target: django-wiki (2026-06-02)

Same harness, a harder real-world target: `django-wiki`'s `testproject` (auth +
article permissions + media + MPTT + plugins; settings *package*; no committed seed
DB; `/` serves the wiki root article). Matrix of 4 engines, 2 models, and thinking-mode
variation — all judged by `pi / openai-codex/gpt-5.5` (independent live judge PASS +
goal-coverage judge `GOAL_REACHED: YES`).

| Engine | Model | Thinking | Stage 2 | Stage 3 | Total | smoke | edits |
|--------|-------|----------|---------|---------|-------|-------|-------|
| Ollama    | qwen 3.6 27b      | off  | 56.2s | 91.2s | 147.4s | /health 200, / 200 | 0 |
| llama.cpp | qwen 3.6 27b      | off  | 46.7s | 71.7s | 118.4s | /health 200, / 200 | 0 |
| MLX       | qwen 3.6 27b      | off  | 60.3s | 72.0s | 132.3s | /health 200, / 200 | 0 |
| llama.cpp | qwen 3.6 27b      | high | 32.2s | 73.7s | 105.9s | /health 200, / 200 | 0 |
| ds4       | DeepSeek V4 Flash | off  | 55.5s | 71.0s | 126.5s | /health 200, / 200 | 0 |
| ds4       | DeepSeek V4 Flash | high | 29.7s | 64.1s |  93.8s | /health 200, / 200 | 0 |

Raw decode speed is a model+engine property (target-independent), so the
django-resume figures hold: ds4 29.9 > MLX 26.9 > llama.cpp 22.5 > Ollama 16.0 tok/s.

## django-resume vs django-wiki

| Engine/model (thinking off) | django-resume total | django-wiki total |
|---|---|---|
| Ollama / qwen      | 171.1s | 147.4s |
| llama.cpp / qwen   | 112.4s | 118.4s |
| MLX / qwen         | 110.2s | 132.3s |
| ds4 / DeepSeek     |  98.7s | 126.5s |

Notes:
- **Same outcome on both targets**: every engine/model/thinking cell reached a working
  packaged wrap with zero model edits (verification-only). Capability was not the
  differentiator — the deterministic scaffold + target generalizations did the
  mechanical wrapping; the models drove verification-first Stages 2–3.
- **django-wiki is the more complex target** (auth, media, MPTT, plugins, settings
  package, runtime-seeded root article) yet stage times are in the same ballpark — the
  extra cost is mostly more migrations/tool execution, not model decode.
- **Thinking mode did not derail here** (unlike ds4 thinking=high on django-resume,
  which errored mid-Stage-3). Because the scaffold fully covered django-wiki, both
  thinking and non-thinking runs were clean verification-only passes — thinking=high was
  even among the fastest. The earlier derail was a property of an under-covered target,
  not of thinking mode per se.
- **Scaffold generalizations django-wiki required** (folded into the deterministic
  scaffold): handle a settings module that is *itself* a package (`__init__` re-exports
  a submodule); use `re_path` for the injected health route (targets that import only
  `re_path`); coerce `Path(BASE_DIR)` (string `BASE_DIR`); make the electron
  `seed_demo_content` step opt-in; and seed a desktop superuser + wiki root article in
  the runtime bootstrap (idempotent, runs on first request even after the launcher's
  migrate).

---

# Third target: django-cast (2026-06-03)

Same harness, a third target: `django-cast` — a Wagtail-based podcast/blog CMS, wrapped
via its `example/` project (settings *package* `example_site.settings`;
`ManifestStaticFilesStorage`; django-vite; no committed seed DB; `/` serves the Wagtail
root page). Matrix of 4 engines, 2 models, and thinking-mode variation — all judged by
`pi / openai-codex/gpt-5.5` (independent live judge PASS + goal-coverage judge
`GOAL_REACHED: YES`).

| Engine | Model | Thinking | Stage 2 | Stage 3 | Total | smoke | edits |
|--------|-------|----------|---------|---------|-------|-------|-------|
| Ollama    | qwen 3.6 27b      | off  | 63.0s | 107.8s | 170.8s | /health 200, / 200 | 0 |
| llama.cpp | qwen 3.6 27b      | off  | 43.8s | 94.8s  | 138.6s | /health 200, / 200 | 0 |
| MLX       | qwen 3.6 27b      | off  | 43.1s | 82.4s  | 125.5s | /health 200, / 200 | 0 |
| llama.cpp | qwen 3.6 27b      | high | 41.7s | 84.6s  | 126.3s | /health 200, / 200 | 0 |
| ds4       | DeepSeek V4 Flash | off  | 37.0s | 87.8s  | 124.8s | /health 200, / 200 | 0 |
| ds4       | DeepSeek V4 Flash | high | 33.3s | 78.5s  | 111.8s | /health 200, / 200 | 0 |

Raw decode speed is a model+engine property (target-independent), so the
django-resume figures hold: ds4 29.9 > MLX 26.9 > llama.cpp 22.5 > Ollama 16.0 tok/s.

## django-resume vs django-wiki vs django-cast

| Engine/model (thinking off) | django-resume | django-wiki | django-cast |
|---|---|---|---|
| Ollama / qwen      | 171.1s | 147.4s | 170.8s |
| llama.cpp / qwen   | 112.4s | 118.4s | 138.6s |
| MLX / qwen         | 110.2s | 132.3s | 125.5s |
| ds4 / DeepSeek     |  98.7s | 126.5s | 124.8s |

Notes:
- **Same outcome on all three targets**: every engine/model/thinking cell reached a
  working packaged wrap with zero model edits (verification-only). Capability was not
  the differentiator — the deterministic scaffold did the mechanical wrapping; the
  models drove verification-first Stages 2–3.
- **django-cast needed NO new scaffold generalizations.** The settings-*package*
  handling added for django-wiki already covered cast's `example_site.settings` package.
  `collectstatic` post-processed 275 files through `ManifestStaticFilesStorage` without
  error, and `/` serves the Wagtail welcome root page (migrate's post-migrate default).
- **Benign `django_vite.W001` warning** (missing Vite manifest for app `default`) is
  expected and does not affect the root page or the smoke. Serving deeper cast
  blog/podcast pages (e.g. `/test-blog/`) additionally needs target-side packaged
  `DJANGO_VITE["cast"]` + plain static storage and is out of scope for this benchmark's
  `/health/ 200 + / 200` contract (documented separately in the April single-harness runs).
- **Thinking=high did not derail on cast** (unlike ds4 thinking=high on django-resume).
  As with django-wiki, full scaffold coverage made both thinking modes clean
  verification-only passes; ds4 thinking=high was in fact the fastest cell (111.8s).
- Reproduction tooling + per-cell logs in `.bench-qwen36/` (`run-cast-matrix.sh`,
  `cast-stage-{2,3}-filled.md`, `cast-judge-prompt.md`, `cast-goal-judge.md`,
  `results-cast-*`).


---

# One-shot (un-staged) variant: django-resume (2026-06-03)

The staged benchmarks above all passed because the deterministic Stage 1 scaffold does
the mechanical wrapping and the model only runs verification-first Stages 2–3. To make
it genuinely hard, this variant drops the scaffold entirely and gives the model the
**original one-shot prompt** (`skills/wrap-existing-django-in-electron/prompt.md`): the
model must author the *entire* wrap (electron/ + Django integration, ~9–36 files) from
scratch in one unattended agentic session, then self-verify. Runner:
`.bench-qwen36/run-oneshot-wrap.sh` (no scaffold). Judged by `pi / openai-codex/gpt-5.5`
(independent live judge + benchmark-success judge `BENCHMARK_RUN_SUCCESSFUL: YES`).

| Subject | Context | Budget | Outcome | What happened |
|---------|---------|--------|---------|---------------|
| gpt-5.5 (frontier control) | 272k | — | **PASS** (7.2 min) | authored 35 files / 2,565 insertions (model-authored; the verifier's npm `package-lock.json` is excluded); packaged smoke `/health/` 200, `/` → `/resume/` 200; node tests pass |
| qwen 3.6 27b (llama.cpp) | 32k | killed at 37 min | **FAIL** | authored only 1 partial Django middleware (`desktop_auth_middleware.py`), never started the `electron/` shell; under heavy context pressure (~24k of its 32k window after reading the skill+refs). Stopped (SIGTERM, `pi_exit=143`) at 37 min to reallocate RAM to ds4 — before its 40-min cap and before a definitive overflow. Evidence: `results-oneshot-llamacpp/{summary,diff-stat,server-evidence}.txt` |
| DeepSeek V4 Flash (ds4.c) | 128k | 50 min | **FAIL** | built `electron/` skeleton + `package.json`, then stalled; timed out |
| DeepSeek V4 Flash (ds4.c) | 128k | 2 h | **FAIL** | exited cleanly (`pi_exit=0`) after ~54 min with 0 files — explored (18 read + 47 bash, 0 writes) and never authored a wrap. The shared 128k ds4-server session overflowed its KV cache during this window, though this run's own committed transcript-summary carries no overflow marker (`error_markers=[]`). Evidence: `results-oneshot-ds4-2h/transcript-summary.txt` (tool usage) + `results-oneshot-ds4-128k-session-server-evidence.txt` (shared-session overflow) |
| DeepSeek V4 Flash (ds4.c) | 128k | 4 h | **FAIL** | context overflow — this run's transcript carries `prompt exceeds context` markers and the shared 128k server logged a KV-cache overflow; self-terminated in ~19 min. Evidence: `results-oneshot-ds4-4h/transcript-summary.txt` (per-run markers) + `results-oneshot-ds4-128k-session-server-evidence.txt` (shared 128k server) |
| DeepSeek V4 Flash (ds4.c) | **256k** | 2 h | **FAIL** | no overflow (reached ~132k); 122 bash explorations, then `finish=error error="invalid tool call"` while emitting a large settings write. Evidence: `results-oneshot-ds4-256k/server-evidence.txt` |

## Staged vs one-shot — the discriminating result

- **Staged**: every engine/model/thinking cell passed on django-resume, django-wiki, and
  django-cast (zero model edits, verification-only). The staged benchmark measures
  "can the model *verify* a scaffold-covered wrap" — near-zero capability signal.
- **One-shot**: only the **frontier** model (gpt-5.5) completed, in ~7 min. **Both local
  models failed**, for layered reasons:
  - qwen 3.6 27b — did not converge: heavy **32k context pressure** (reached ~24k after
    reading the 505-line skill + architecture + spec) with only a partial Django
    middleware and no Electron shell when it was stopped at 37 min. (Stopped to free RAM
    for ds4 before the 40-min cap, so a full 32k overflow was not reached — but it was
    nowhere near a working wrap.)
  - DeepSeek V4 Flash — **128k context overflow** is directly evidenced for the 4h run
    (its transcript carries `prompt exceeds context` markers) and for the shared 128k
    server session (KV-cache capacity exceeded). The 2h run's own transcript shows only
    exploration (47 bash, 0 writes) and a clean exit with no wrap, so its failure isn't
    independently tied to an overflow marker. Given **256k** headroom ds4 stopped
    overflowing but still failed on an **unreliable large-file tool call** (`invalid
    tool call`) after heavy exploration. Time was *not* the limiter (it self-terminated
    well within the 2h/4h budgets); context and large-write tool-call reliability were.
- This is exactly why the staged workflow exists: its own description says it is for when
  "the one-shot wrap prompt is too large for the model you want to run locally… the run
  stalls, drifts, or corrupts long files… the model has a smaller or less reliable
  context window." The one-shot benchmark makes that gap measurable here: **the frontier
  control one-shot the wrap in minutes; the two local configurations tested (qwen 3.6 27b
  @32k, DeepSeek V4 Flash @128k/256k) did not** — blocked by context limits and
  large-write tool-call reliability, not wall time. (This is evidence from two local
  configs on one target, not a universal claim that no local model can one-shot a wrap.)

Reproduction: `.bench-qwen36/run-oneshot-wrap.sh`, `oneshot-judge-prompt.md`,
`oneshot-goal-judge.md`. Per-cell evidence is in `results-oneshot-*/` — small
`summary.txt`, `diff-stat.txt`, `transcript-summary.txt` (tool-call breakdown), and
`server-evidence.txt` (the cited context/tool-call errors from the model server logs);
the pi judge verdicts are in `results-oneshot-JUDGE-verdicts.md`. The multi-GB raw json
transcripts are gitignored (`.gitignore`), not committed. The original one-shot
prompt/skill is `skills/wrap-existing-django-in-electron/`.

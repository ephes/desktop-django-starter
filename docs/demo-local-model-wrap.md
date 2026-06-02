# Local-Model Wrap Demo (Pi + Ollama / llama.cpp / MLX / ds4)

Experimental lab runbook for demoing the staged `django-resume` Electron wrap
driven by a local model through Pi, on each of four serving runtimes. It is the
companion to the runtime comparison in [Agent Use](agent-use.md) (see its
"Local runtime comparison" section).

The commands below assume the lab layout used to produce the comparison
(`~/projects/desktop-django-starter`, `~/projects/django-resume`, and the local
model servers). The reproduction tooling lives in the starter checkout under
`.bench-qwen36/`.

## What the demo does

1. Makes a clean clone of `django-resume` (the target).
2. Runs the deterministic **Stage 1 scaffold** (not the model) — lays down
   `electron/` and the Django desktop baseline.
3. Drives the local model through Pi for **Stage 2** (Electron) and **Stage 3**
   (Django) — verification-first; on this target both are zero-edit passes.
4. Runs an independent **Pi judge** (`openai-codex/gpt-5.5`) that re-runs the
   packaged smoke and returns PASS/FAIL.

The mechanical wrapping is done by Stage 1; the model's job is to drive and verify
Stages 2–3. That is what these runs measure.

## Prerequisites (host: Apple Silicon, 128 GB used here)

| Need | Install / location |
|---|---|
| `pi` | already installed (`pi --version`) |
| Source repo | `~/projects/django-resume` (clean checkout) |
| Starter + scaffold | `~/projects/desktop-django-starter` (this repo) |
| Ollama | `ollama serve` running; model `qwen36-27b-tools` (built below) |
| llama.cpp | `brew install llama.cpp`; GGUF `~/models/gguf/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf` |
| MLX | `uv tool install mlx-lm`; model `mlx-community/Qwen3.6-27B-4bit` (HF cache) |
| ds4 | built `ds4-server` + `ds4flash.gguf` in `~/workspaces/ds4-pi-django-resume/ds4-pi` |
| `uv`, `node`, `npm` | for the Django/Electron verification commands |

### One-time: build the tool-capable Ollama model

The raw Ollama GGUF import shipped a bare `{{ .Prompt }}` template and cannot call
tools. Rebuild it with the Qwen3 ChatML template:

```bash
cd ~/projects/desktop-django-starter/.bench-qwen36
ollama create qwen36-27b-tools -f Modelfile.qwen36-27b-tools
```

## Start the model server for the runtime you want to demo

Pick one. Each exposes an OpenAI-compatible `/v1` endpoint that a Pi provider
extension in `.bench-qwen36/` points at.

```bash
# Ollama — already serving on :11434, nothing to start (uses qwen36-27b-tools)

# llama.cpp — native tool calling via --jinja (reads the GGUF chat template)
llama-server -m ~/models/gguf/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf \
  --jinja --host 127.0.0.1 --port 8080 -c 32768 -ngl 999

# MLX
mlx_lm.server --model mlx-community/Qwen3.6-27B-4bit --host 127.0.0.1 --port 8081

# ds4 (DeepSeek V4 Flash) — port 8002 to avoid the default :8000
cd ~/workspaces/ds4-pi-django-resume/ds4-pi
./ds4-server -m ds4flash.gguf --host 127.0.0.1 --port 8002 -c 32768 \
  --kv-disk-dir /tmp/ds4-bench-kv --kv-disk-space-mb 8192
```

Wait until ready: `curl -s http://127.0.0.1:<port>/v1/models` returns the model.
(llama.cpp loads in seconds; ds4 maps 86 GB and may download weights first.)

## Run the full wrap (one command)

The runner does a clean `rm -rf` + fresh `git clone` of the target, Stage 1
scaffold, `npm install`, then drives Pi for Stage 2 + Stage 3, then an independent
verification smoke. Results land in `results-<label>/`.

```bash
cd ~/projects/desktop-django-starter/.bench-qwen36
EXT_LOCAL=$PWD/pi-localserver-provider.ts   # llamacpp + mlx
EXT_OLLAMA=$PWD/pi-ollama-provider.ts
EXT_DS4=$PWD/pi-ds4local-provider.ts

# usage: ./run-staged-wrap.sh <label> <pi-extension> <provider> <model>
./run-staged-wrap.sh ollama   "$EXT_OLLAMA" ollama   qwen36-27b-tools
./run-staged-wrap.sh llamacpp "$EXT_LOCAL"  llamacpp qwen3.6-27b
./run-staged-wrap.sh mlx      "$EXT_LOCAL"  mlx      mlx-community/Qwen3.6-27B-4bit
./run-staged-wrap.sh ds4      "$EXT_DS4"    ds4local deepseek-v4-flash
```

A pass prints `health200=1 root302=1 resume200=1` and `git_changed_files=11`
(the 9 scaffold files + `uv.lock` + `.stage/`, i.e. zero model edits).

## Run the model stages manually (better for a live demo)

If you want to show the agent working step by step instead of the runner:

```bash
TARGET=~/projects/django-resume-clean
rm -rf "$TARGET" && git clone ~/projects/django-resume "$TARGET"
~/projects/desktop-django-starter/skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh "$TARGET"
npm --prefix "$TARGET/electron" install
cd "$TARGET"

EXT=~/projects/desktop-django-starter/.bench-qwen36/pi-localserver-provider.ts
B=~/projects/desktop-django-starter/.bench-qwen36

# Stage 2 (Electron). Swap --provider/--model for the runtime you started.
pi -e "$EXT" --provider llamacpp --model qwen3.6-27b \
   --no-session --thinking off -nc -ns -np -p "$(cat $B/stage-2-filled.md)"

# Stage 3 (Django).
pi -e "$EXT" --provider llamacpp --model qwen3.6-27b \
   --no-session --thinking off -nc -ns -np -p "$(cat $B/stage-3-filled.md)"
```

Provider/model per runtime:

| Runtime | `--provider` | `--model` | extension |
|---|---|---|---|
| Ollama | `ollama` | `qwen36-27b-tools` | `pi-ollama-provider.ts` |
| llama.cpp | `llamacpp` | `qwen3.6-27b` | `pi-localserver-provider.ts` |
| MLX | `mlx` | `mlx-community/Qwen3.6-27B-4bit` | `pi-localserver-provider.ts` |
| ds4 | `ds4local` | `deepseek-v4-flash` | `pi-ds4local-provider.ts` |

```{note}
Keep `--thinking off`. In thinking mode ds4 was ~3x slower and derailed Stage 3
on malformed inline tool output. Non-thinking was both fastest and cleanest.
```

## Independent Pi judge

```bash
cd ~/projects/django-resume-clean
pi --no-session -nc --print "$(cat ~/projects/desktop-django-starter/.bench-qwen36/judge-prompt.md)"
```

It ends with `VERDICT: PASS` (or FAIL) after re-running the packaged smoke itself.

## Absolute time per model — target 1: django-resume (Stage 2 + Stage 3)

Measured 2026-06-02 on studio (Apple M4 Max, 128 GB). Stage times are wall-clock
including the fixed tool execution each stage runs (uv, npm, node tests, smoke).

| Model / runtime | Stage 2 | Stage 3 | **Total wrap time** |
|---|---|---|---|
| Ollama — qwen 3.6 27b Q4_K_M | 73.7s | 97.4s | **171.1s (~2m51s)** |
| llama.cpp — qwen 3.6 27b Q4_K_M | 41.7s | 70.7s | **112.4s (~1m52s)** |
| MLX — qwen 3.6 27b 4-bit | 40.0s | 70.2s | **110.2s (~1m50s)** |
| ds4 — DeepSeek V4 Flash (non-thinking) | 28.6s | 70.1s | **98.7s (~1m39s)** |
| ds4 — DeepSeek V4 Flash (thinking=high, 06-01) | 86.4s | 318.0s | **404.4s (~6m44s)** |

Add roughly `npm install` (~3–20s, cached after first run) + Stage 1 scaffold
(~0.2s) + a ~7s verification smoke for the full end-to-end. Raw decode speed
(isolated): ds4 29.9 > MLX 26.9 > llama.cpp 22.5 > Ollama 16.0 tok/s. For a smooth
demo, start the server and do one warm-up request before the audience is watching.

## Second target: django-wiki (harder app)

The same harness was replicated against a harder real-world target — `django-wiki`'s
`testproject` (auth + article permissions + media + MPTT + plugins; a settings
*package*; no committed seed DB; `/` serves the wiki root article). A 6-cell matrix (4
engines × 2 models × thinking off/high) all reached a working packaged wrap with **zero
model edits**, judged by `pi / openai-codex/gpt-5.5` (live judge PASS + goal-coverage
judge `GOAL_REACHED: YES`).

| Engine | Model | Thinking | Stage 2 | Stage 3 | **Total** |
|---|---|---|---|---|---|
| Ollama | qwen 3.6 27b | off | 56.2s | 91.2s | **147.4s** |
| llama.cpp | qwen 3.6 27b | off | 46.7s | 71.7s | **118.4s** |
| MLX | qwen 3.6 27b | off | 60.3s | 72.0s | **132.3s** |
| llama.cpp | qwen 3.6 27b | high | 32.2s | 73.7s | **105.9s** |
| ds4 | DeepSeek V4 Flash | off | 55.5s | 71.0s | **126.5s** |
| ds4 | DeepSeek V4 Flash | high | 29.7s | 64.1s | **93.8s** |

Same outcome as django-resume (zero edits, verification-only), same ballpark times
despite the heavier app. Notably, **thinking=high did not derail here** (unlike ds4
thinking=high on django-resume) — because the deterministic scaffold fully covered
django-wiki, both thinking modes were clean passes. The full cross-target comparison is
in `.bench-qwen36/RUNTIME-COMPARISON.md`.

### Reproduce django-wiki via the Pi agent from a clean workspace

```bash
# 1. Get a clean django-wiki source clone (the runner re-clones from here per run)
git clone https://github.com/django-wiki/django-wiki ~/projects/django-wiki

# 2. Start the model server you want (same as the django-resume section above):
#    Ollama (:11434, qwen36-27b-tools) / llama.cpp (:8080) / MLX (:8081) / ds4 (:8002)

# 3. Run a wrap cell. The runner is env-parametrized for the target + prompts.
cd ~/projects/desktop-django-starter/.bench-qwen36
export BENCH_SRC=~/projects/django-wiki BENCH_TGT=~/projects/django-wiki-clean
export BENCH_S2=$PWD/wiki-stage-2-filled.md BENCH_S3=$PWD/wiki-stage-3-filled.md

# qwen on each engine (thinking off):
BENCH_THINKING=off ./run-staged-wrap.sh wiki-ollama   "$PWD/pi-ollama-provider.ts"      ollama   qwen36-27b-tools
BENCH_THINKING=off ./run-staged-wrap.sh wiki-llamacpp "$PWD/pi-localserver-provider.ts" llamacpp qwen3.6-27b
BENCH_THINKING=off ./run-staged-wrap.sh wiki-mlx      "$PWD/pi-localserver-provider.ts" mlx      mlx-community/Qwen3.6-27B-4bit

# DeepSeek V4 Flash on ds4, and thinking-mode variation (high):
BENCH_THINKING=off  ./run-staged-wrap.sh wiki-ds4 "$PWD/pi-ds4local-provider.ts" ds4local deepseek-v4-flash
BENCH_THINKING=high BENCH_OUT_SUFFIX=-thinkhigh ./run-staged-wrap.sh wiki-ds4 "$PWD/pi-ds4local-provider.ts" ds4local deepseek-v4-flash
BENCH_THINKING=high BENCH_OUT_SUFFIX=-thinkhigh ./run-staged-wrap.sh wiki-llamacpp "$PWD/pi-localserver-provider.ts" llamacpp qwen3.6-27b
```

Each run prints `health200=1 root200=1 app_served=1` and `git_changed_files=8` on a
clean pass (the deterministic scaffold output + `uv.lock`, i.e. zero model edits), and
writes logs under `results-wiki-<label>/`.

To run the stages manually for a live demo, use the same `pi -e ... --provider ...`
invocation as the django-resume section but with the wiki prompts
(`wiki-stage-2-filled.md`, `wiki-stage-3-filled.md`). Judge a single result with
`wiki-judge-prompt.md`, and confirm full coverage across all cells with
`wiki-goal-judge.md`:

```bash
cd ~/projects/django-wiki-clean
pi --no-session -nc --print "$(sed 's/{{MODEL_DESC}}/the model under test/' \
  ~/projects/desktop-django-starter/.bench-qwen36/wiki-judge-prompt.md)"

pi --no-session -nc --print "$(cat ~/projects/desktop-django-starter/.bench-qwen36/wiki-goal-judge.md)"
```

## Third target: django-cast (Wagtail CMS)

The same harness was replicated again against `django-cast` — a Wagtail-based
podcast/blog CMS using its `example/` project (settings *package*
`example_site.settings`; `ManifestStaticFilesStorage`; django-vite; no committed seed
DB; `/` serves the Wagtail root page). The deterministic Stage 1 scaffold already
covered this target with **no new generalizations** (the settings-package handling
added for django-wiki was sufficient), so the same 6-cell matrix (4 engines × 2 models
× thinking off/high) ran as clean verification-only passes, judged by
`pi / openai-codex/gpt-5.5` (live judge PASS + goal-coverage judge `GOAL_REACHED: YES`).

The packaged smoke contract matches the other targets: `GET /health/` 200 and `GET /`
200 (the Wagtail welcome root page). A benign `django_vite.W001` warning about a
missing Vite manifest for app `default` is expected and does not affect the root page
or the smoke; serving deeper cast blog/podcast pages (e.g. `/test-blog/`) additionally
needs target-side packaged `DJANGO_VITE["cast"]` + plain static storage and is out of
scope for this benchmark's contract.

| Engine | Model | Thinking | Stage 2 | Stage 3 | **Total** |
|---|---|---|---|---|---|
| Ollama | qwen 3.6 27b | off | 63.0s | 107.8s | **170.8s** |
| llama.cpp | qwen 3.6 27b | off | 43.8s | 94.8s | **138.6s** |
| MLX | qwen 3.6 27b | off | 43.1s | 82.4s | **125.5s** |
| llama.cpp | qwen 3.6 27b | high | 41.7s | 84.6s | **126.3s** |
| ds4 | DeepSeek V4 Flash | off | 37.0s | 87.8s | **124.8s** |
| ds4 | DeepSeek V4 Flash | high | 33.3s | 78.5s | **111.8s** |

All six cells `app_served=1` (smoke `/health/` 200, `/` 200) with zero model edits
(`git_changed_files=9`). The cross-target comparison is in
`.bench-qwen36/RUNTIME-COMPARISON.md`.

### Reproduce django-cast via the Pi agent from a clean workspace

```bash
# 1. django-cast source clone (the runner re-clones from here per run)
git clone https://github.com/ephes/django-cast ~/projects/django-cast

# 2. Start the model server you want (same as the django-resume section above):
#    Ollama (:11434, qwen36-27b-tools) / llama.cpp (:8080) / MLX (:8081) / ds4 (:8002)

# 3. Run a wrap cell. The runner is env-parametrized for the target + prompts.
cd ~/projects/desktop-django-starter/.bench-qwen36
export BENCH_SRC=~/projects/django-cast BENCH_TGT=~/projects/django-cast-clean
export BENCH_S2=$PWD/cast-stage-2-filled.md BENCH_S3=$PWD/cast-stage-3-filled.md

# qwen on each engine (thinking off):
BENCH_THINKING=off ./run-staged-wrap.sh cast-ollama   "$PWD/pi-ollama-provider.ts"      ollama   qwen36-27b-tools
BENCH_THINKING=off ./run-staged-wrap.sh cast-llamacpp "$PWD/pi-localserver-provider.ts" llamacpp qwen3.6-27b
BENCH_THINKING=off ./run-staged-wrap.sh cast-mlx      "$PWD/pi-localserver-provider.ts" mlx      mlx-community/Qwen3.6-27B-4bit

# DeepSeek V4 Flash on ds4, and thinking-mode variation (high):
BENCH_THINKING=off  ./run-staged-wrap.sh cast-ds4 "$PWD/pi-ds4local-provider.ts" ds4local deepseek-v4-flash
BENCH_THINKING=high BENCH_OUT_SUFFIX=-thinkhigh ./run-staged-wrap.sh cast-ds4 "$PWD/pi-ds4local-provider.ts" ds4local deepseek-v4-flash
BENCH_THINKING=high BENCH_OUT_SUFFIX=-thinkhigh ./run-staged-wrap.sh cast-llamacpp "$PWD/pi-localserver-provider.ts" llamacpp qwen3.6-27b
```

Or drive all six cells (with automatic server start/stop) via
`./run-cast-matrix.sh`. Judge a single result with `cast-judge-prompt.md` and confirm
full coverage with `cast-goal-judge.md`:

```bash
cd ~/projects/django-cast-clean
pi --no-session -nc --print "$(sed 's/{{MODEL_DESC}}/the model under test/' \
  ~/projects/desktop-django-starter/.bench-qwen36/cast-judge-prompt.md)"

pi --no-session -nc --print "$(cat ~/projects/desktop-django-starter/.bench-qwen36/cast-goal-judge.md)"
```

## Cleanup

```bash
pkill -f "llama-server -m .*Qwen3.6-27B"       # free ~16 GB
pkill -f "mlx_lm.server --model mlx-community"  # free ~15 GB
pkill -f "ds4-server -m ds4flash.gguf"          # free ~86 GB
rm -rf ~/projects/django-resume-clean ~/projects/django-wiki-clean ~/projects/django-cast-clean
```

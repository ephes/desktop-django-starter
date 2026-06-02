#!/usr/bin/env bash
# Drive the full 6-cell django-cast staged-wrap matrix, mirroring the django-wiki
# matrix. Starts/stops the llama.cpp / MLX / ds4 servers around their cells so the
# large weights are never all resident at once. Ollama is assumed already serving.
set -uo pipefail

BENCH=/Users/jochen/projects/desktop-django-starter/.bench-qwen36
export BENCH_SRC=/Users/jochen/projects/django-cast
export BENCH_TGT=/Users/jochen/projects/django-cast-clean
export BENCH_S2=$BENCH/cast-stage-2-filled.md
export BENCH_S3=$BENCH/cast-stage-3-filled.md
EXT_OLLAMA=$BENCH/pi-ollama-provider.ts
EXT_LOCAL=$BENCH/pi-localserver-provider.ts
EXT_DS4=$BENCH/pi-ds4local-provider.ts
LLAMA_GGUF=/Users/jochen/models/gguf/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf
DS4_DIR=/Users/jochen/workspaces/ds4-pi-django-resume/ds4-pi

log() { echo "==== [$(date +%H:%M:%S)] $* ===="; }

wait_ready() { # port label timeout
  local port="$1" label="$2" deadline=$((SECONDS + ${3:-180}))
  while (( SECONDS < deadline )); do
    if curl -s -m 3 "http://127.0.0.1:$port/v1/models" >/dev/null 2>&1; then
      log "$label ready on :$port"; return 0
    fi
    sleep 3
  done
  log "$label DID NOT become ready on :$port"; return 1
}

run_cell() { # label ext provider model thinking suffix
  local label="$1" ext="$2" provider="$3" model="$4" thinking="$5" suffix="${6:-}"
  log "CELL $label$suffix (thinking=$thinking)"
  BENCH_THINKING="$thinking" BENCH_OUT_SUFFIX="$suffix" \
    "$BENCH/run-staged-wrap.sh" "$label" "$ext" "$provider" "$model"
}

############ 1. Ollama (already up) — qwen off ############
# Run separately as the pipeline-validation cell; skip here to avoid redoing it.
# To include it, uncomment:
# wait_ready 11434 "Ollama" 30 && run_cell cast-ollama "$EXT_OLLAMA" ollama qwen36-27b-tools off ""

############ 2. llama.cpp — qwen off + qwen high ############
log "starting llama-server :8080"
llama-server -m "$LLAMA_GGUF" --jinja --host 127.0.0.1 --port 8080 -c 32768 -ngl 999 \
  > /tmp/cast-llama-server.log 2>&1 &
LLAMA_PID=$!
if wait_ready 8080 "llama.cpp" 180; then
  run_cell cast-llamacpp "$EXT_LOCAL" llamacpp qwen3.6-27b off ""
  run_cell cast-llamacpp "$EXT_LOCAL" llamacpp qwen3.6-27b high "-thinkhigh"
fi
kill "$LLAMA_PID" 2>/dev/null; wait "$LLAMA_PID" 2>/dev/null
log "llama-server stopped"

############ 3. MLX — qwen off ############
log "starting mlx_lm.server :8081"
mlx_lm.server --model mlx-community/Qwen3.6-27B-4bit --host 127.0.0.1 --port 8081 \
  > /tmp/cast-mlx-server.log 2>&1 &
MLX_PID=$!
if wait_ready 8081 "MLX" 240; then
  run_cell cast-mlx "$EXT_LOCAL" mlx mlx-community/Qwen3.6-27B-4bit off ""
fi
kill "$MLX_PID" 2>/dev/null; wait "$MLX_PID" 2>/dev/null
log "mlx_lm.server stopped"

############ 4. ds4 — DeepSeek off + high ############
log "starting ds4-server :8002"
( cd "$DS4_DIR" && ./ds4-server -m ds4flash.gguf --host 127.0.0.1 --port 8002 -c 32768 \
  --kv-disk-dir /tmp/ds4-cast-kv --kv-disk-space-mb 8192 ) > /tmp/cast-ds4-server.log 2>&1 &
DS4_PID=$!
if wait_ready 8002 "ds4" 360; then
  run_cell cast-ds4 "$EXT_DS4" ds4local deepseek-v4-flash off ""
  run_cell cast-ds4 "$EXT_DS4" ds4local deepseek-v4-flash high "-thinkhigh"
fi
kill "$DS4_PID" 2>/dev/null; wait "$DS4_PID" 2>/dev/null
log "ds4-server stopped"

log "MATRIX COMPLETE — summaries:"
for d in cast-ollama cast-llamacpp cast-llamacpp-thinkhigh cast-mlx cast-ds4 cast-ds4-thinkhigh; do
  echo "---- results-$d ----"
  cat "$BENCH/results-$d/summary.txt" 2>/dev/null || echo "(no summary)"
done

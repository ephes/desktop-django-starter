#!/usr/bin/env bash
# Drive a local model through the staged Electron wrap for one runtime and record
# per-stage wall-clock. Target/source/prompts/thinking-mode are env-overridable so
# the same runner works for django-resume (defaults) and django-wiki.
#
# Usage:
#   run-staged-wrap.sh <label> <pi-extension> <provider> <model>
# Env overrides:
#   BENCH_SRC   source repo to clone   (default ~/projects/django-resume)
#   BENCH_TGT   disposable target path (default ~/projects/django-resume-clean)
#   BENCH_S2    stage-2 prompt file    (default .bench-qwen36/stage-2-filled.md)
#   BENCH_S3    stage-3 prompt file    (default .bench-qwen36/stage-3-filled.md)
#   BENCH_THINKING  pi --thinking level (default off)
#   BENCH_OUT_SUFFIX  appended to results dir name (e.g. "-thinkhigh")
set -uo pipefail

LABEL="$1"; EXT="$2"; PROVIDER="$3"; MODEL="$4"
STARTER=/Users/jochen/projects/desktop-django-starter
BENCH="$STARTER/.bench-qwen36"
SRC="${BENCH_SRC:-/Users/jochen/projects/django-resume}"
TARGET="${BENCH_TGT:-/Users/jochen/projects/django-resume-clean}"
S2="${BENCH_S2:-$BENCH/stage-2-filled.md}"
S3="${BENCH_S3:-$BENCH/stage-3-filled.md}"
THINKING="${BENCH_THINKING:-off}"
OUT="$BENCH/results-${LABEL}${BENCH_OUT_SUFFIX:-}"
mkdir -p "$OUT"
SYS="You are a focused coding agent doing ONE narrow stage of work. Use your bash tool to run the listed verification commands in order. Some commands (uv, smoke) take 10-60s; wait for each to finish. Be concise. Stop as soon as all checks pass. Do not explore beyond the listed files."

now() { python3 -c 'import time;print(f"{time.time():.3f}")'; }
run_pi() { # promptfile logfile timeout
  local prompt; prompt="$(cat "$1")"
  timeout "$3" pi -e "$EXT" --provider "$PROVIDER" --model "$MODEL" \
    --no-session --thinking "$THINKING" -nc -ns -np \
    --append-system-prompt "$SYS" -p "$prompt" > "$2" 2>&1
  echo $?
}

echo "[$LABEL] fresh clone + Stage 1 scaffold + install (src=$SRC tgt=$TARGET thinking=$THINKING)"
rm -rf "$TARGET"
git clone -q "$SRC" "$TARGET"
"$STARTER/skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh" "$TARGET" >/dev/null 2>&1 || { echo "scaffold FAILED"; exit 1; }
npm --prefix "$TARGET/electron" install >/dev/null 2>&1 || { echo "install FAILED"; exit 1; }

cd "$TARGET"

t0=$(now)
echo "[$LABEL] Stage 2 (Electron) ..."
s2_exit=$(run_pi "$S2" "$OUT/stage2.log" 900)
t1=$(now)
echo "[$LABEL] Stage 3 (Django) ..."
s3_exit=$(run_pi "$S3" "$OUT/stage3.log" 1200)
t2=$(now)

s2_dur=$(python3 -c "print(f'{$t1-$t0:.1f}')")
s3_dur=$(python3 -c "print(f'{$t2-$t1:.1f}')")

echo "[$LABEL] independent verification smoke ..."
timeout 180 npm --prefix electron run smoke:packaged > "$OUT/verify-smoke.log" 2>&1
smoke_exit=$?
git status --short > "$OUT/git-status.txt"

health200=$(grep -c 'GET /health/ HTTP/1.1" 200' "$OUT/verify-smoke.log")
root200=$(grep -c 'GET / HTTP/1.1" 200' "$OUT/verify-smoke.log")
root302=$(grep -c 'GET / HTTP/1.1" 302' "$OUT/verify-smoke.log")
# "app served" = health ok AND the root either rendered (200) or redirected into the app (302)
if [ "$health200" -ge 1 ] && { [ "$root200" -ge 1 ] || [ "$root302" -ge 1 ]; }; then app_served=1; else app_served=0; fi

{
  echo "label=$LABEL"
  echo "provider=$PROVIDER model=$MODEL thinking=$THINKING"
  echo "src=$SRC target=$TARGET"
  echo "stage2_exit=$s2_exit stage2_seconds=$s2_dur"
  echo "stage3_exit=$s3_exit stage3_seconds=$s3_dur"
  echo "verify_smoke_exit=$smoke_exit"
  echo "health200=$health200 root200=$root200 root302=$root302 app_served=$app_served"
  echo "git_changed_files=$(wc -l < "$OUT/git-status.txt" | tr -d ' ')"
} | tee "$OUT/summary.txt"

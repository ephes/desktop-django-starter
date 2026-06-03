#!/usr/bin/env bash
# Drive a model through the ORIGINAL one-shot wrap prompt (no deterministic Stage 1
# scaffold): the model must author the entire Electron wrap from scratch in one
# unattended agentic session. Then verify (electron tests + packaged smoke) and
# record pass/fail + failure mode. This is the hard, capability-discriminating variant
# of the staged benchmark.
#
# Usage:
#   run-oneshot-wrap.sh <label> <pi-extension|none> <provider> <model>
# Env overrides:
#   BENCH_SRC   source repo to clone   (default ~/projects/django-resume)
#   BENCH_TGT   disposable target path (default ~/projects/django-resume-clean)
#   BENCH_THINKING  pi --thinking level (default off)
#   BENCH_TIMEOUT   per-run seconds    (default 2400 = 40 min)
#   BENCH_OUT_SUFFIX  appended to results dir name
set -uo pipefail

LABEL="$1"; EXT="$2"; PROVIDER="$3"; MODEL="$4"
STARTER=/Users/jochen/projects/desktop-django-starter
BENCH="$STARTER/.bench-qwen36"
SRC="${BENCH_SRC:-/Users/jochen/projects/django-resume}"
TARGET="${BENCH_TGT:-/Users/jochen/projects/django-resume-clean}"
THINKING="${BENCH_THINKING:-off}"
TIMEOUT="${BENCH_TIMEOUT:-2400}"
PROMPT="$STARTER/skills/wrap-existing-django-in-electron/prompt.md"
OUT="$BENCH/results-oneshot-${LABEL}${BENCH_OUT_SUFFIX:-}"
rm -rf "$OUT"; mkdir -p "$OUT"   # clear stale artifacts from a prior run of this label

now() { python3 -c 'import time;print(f"{time.time():.3f}")'; }

echo "[$LABEL] fresh clone (NO Stage 1 scaffold) src=$SRC tgt=$TARGET thinking=$THINKING"
rm -rf "$TARGET"
git clone -q "$SRC" "$TARGET" || { echo "[$LABEL] ERROR: git clone failed"; exit 1; }
cd "$TARGET" || { echo "[$LABEL] ERROR: cd to target failed"; exit 1; }

# The one-shot prompt references ../desktop-django-starter as reference material; the
# target clone is a sibling of the starter, so relative paths resolve.
pi_args=(--provider "$PROVIDER" --model "$MODEL" --no-session --thinking "$THINKING" -nc -ns -np)
# Optional streaming mode (e.g. json) so a timeout-killed run still leaves a partial
# transcript instead of pi's buffered --print flushing nothing on SIGTERM.
[ -n "${BENCH_PI_MODE:-}" ] && pi_args+=(--mode "$BENCH_PI_MODE")
[ "$EXT" != "none" ] && pi_args=(-e "$EXT" "${pi_args[@]}")

t0=$(now)
echo "[$LABEL] one-shot wrap (timeout ${TIMEOUT}s) ..."
# </dev/null so pi never blocks waiting on a TTY stdin when launched detached.
timeout "$TIMEOUT" pi "${pi_args[@]}" -p "$(cat "$PROMPT")" </dev/null > "$OUT/oneshot.log" 2>&1
pi_exit=$?
t1=$(now)
dur=$(python3 -c "print(f'{$t1-$t0:.1f}')")

# Capture the MODEL-AUTHORED diff BEFORE verification mutates the clone. Otherwise
# `npm install` (electron/package-lock.json + node_modules) and the smoke (.stage/)
# would be counted as if the model wrote them, inflating files_changed/insertions.
git add -A >/dev/null 2>&1
git diff --cached --stat > "$OUT/diff-stat.txt" 2>/dev/null
files_changed=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')
git reset -q >/dev/null 2>&1

# --- best-effort verification of whatever the model produced ---
# grep -c prints 0 AND exits 1 on no matches; `|| true` keeps the 0 without appending
# a second one (a `|| echo 0` would yield "0\n0" and corrupt the summary).
count() { grep -c "$1" "$2" 2>/dev/null || true; }
electron_exists=0; npm_ok=0; node_tests="NA"; smoke_exit="NA"; health200=0; root200=0; root302=0; resume200=0
if [ -d electron ] && [ -f electron/package.json ]; then
  electron_exists=1
  if npm --prefix electron install >"$OUT/npm.log" 2>&1; then npm_ok=1; fi
  if ls electron/scripts/*.test.cjs >/dev/null 2>&1; then
    if node --test electron/scripts/*.test.cjs >"$OUT/nodetests.log" 2>&1; then node_tests="pass"; else node_tests="fail"; fi
  fi
  if [ "$npm_ok" = "1" ] && npm --prefix electron run | grep -q "smoke:packaged"; then
    timeout 200 npm --prefix electron run smoke:packaged > "$OUT/verify-smoke.log" 2>&1
    smoke_exit=$?
    health200=$(count 'GET /health/ HTTP/1.1" 200' "$OUT/verify-smoke.log")
    root200=$(count 'GET / HTTP/1.1" 200' "$OUT/verify-smoke.log")
    root302=$(count 'GET / HTTP/1.1" 302' "$OUT/verify-smoke.log")
    resume200=$(count 'GET /resume/ HTTP/1.1" 200' "$OUT/verify-smoke.log")
  fi
fi
# app_served = the packaged HTTP app actually served correctly (independent of node
# tests): smoke exits cleanly, health 200, and the app root renders a 200 — either
# directly (/ -> 200) or via a redirect (/ -> 302) whose target (e.g. /resume/)
# returns 200. A bare 302 with no served 200 does NOT count.
app_served=0
if [ "$smoke_exit" = "0" ] && [ "$health200" -ge 1 ] \
   && { [ "$root200" -ge 1 ] || { [ "$root302" -ge 1 ] && [ "$resume200" -ge 1 ]; }; }; then
  app_served=1
fi
# A clean one-shot PASS additionally requires the copied Node test harness to be
# present AND passing (the prompt requires adapting it — a served app with no/failing
# tests is not a clean pass).
if [ "$app_served" = 1 ] && [ "$node_tests" = "pass" ]; then outcome=PASS; else outcome=FAIL; fi

# diff-stat.txt / files_changed were captured pre-verification above (model-authored).

{
  echo "label=$LABEL"
  echo "provider=$PROVIDER model=$MODEL thinking=$THINKING"
  echo "pi_exit=$pi_exit (124=timeout, 143=SIGTERM/killed) duration_seconds=$dur"
  echo "electron_exists=$electron_exists npm_install_ok=$npm_ok node_tests=$node_tests"
  echo "smoke_exit=$smoke_exit health200=$health200 root200=$root200 root302=$root302 resume200=$resume200 app_served=$app_served"
  echo "files_changed=$files_changed"
  echo "outcome=$outcome"
} | tee "$OUT/summary.txt"

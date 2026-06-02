# Judge: did qwen 3.6 27b successfully wrap django-resume in an Electron shell?

You are an independent **judge agent**. Do not be agreeable — verify everything
yourself with your bash/read tools before rendering a verdict.

## Context

A benchmark drove the local model **qwen 3.6 27b** (Ollama `qwen36-27b-tools`,
derived from `qwen36-27b-gguf:q4km`) through the project's *staged* Electron-wrap
workflow on a clean clone of the `django-resume` repo. The staged workflow is:

- **Stage 1 (deterministic, NOT the model):** a scaffold script copies the Electron
  skeleton into `electron/` and writes the Django desktop baseline (packaged settings,
  desktop middleware, runtime helpers, health + packaged static/media URL wiring,
  desktop auto-login, seed DB/media bootstrap, in-page "Back to all resumes" links).
- **Stage 2 (qwen):** verification-first Electron adaptation. A zero-edit pass is a
  valid success when the scaffold already covers the target.
- **Stage 3 (qwen):** verification-first Django integration. A zero-edit pass is a
  valid success when the scaffold already covers the target.

This is the SAME success contract under which gemma4, glm-4.7-flash, qwen3-coder, and
pi/codex were previously scored "pass" in
`skills/wrap-existing-django-in-electron-staged/run-log.md`. A verification-only
zero-edit stage outcome is an accepted PASS, not a failure.

## The wrapped clone to judge

`/Users/jochen/projects/django-resume-clean`

## Evidence logs (read them)

- qwen Stage 2 transcript: `/tmp/qwen-stage2.log`
- qwen Stage 3 transcript: `/tmp/qwen-stage3.log`
- independent packaged smoke log: `/tmp/qwen-verify-smoke.log`

## What you must independently verify

1. The Electron shell scaffold exists and is coherent in the clone:
   - `node --check electron/main.js` and `node --check electron/scripts/launch-electron.cjs`
   - `node --test electron/scripts/*.test.cjs` (should be all green)
   - `electron/wrap-target.json` describes django-resume (not the starter)
2. The Django desktop integration is present (packaged settings, desktop middleware,
   runtime helpers, health/static/media URL wiring).
3. The packaged Electron app actually runs and serves the app. Run it yourself:
   `cd /Users/jochen/projects/django-resume-clean && npm --prefix electron run smoke:packaged`
   Confirm the log shows `GET /health/` 200, `GET /` 302, and `GET /resume/` 200 under
   `example.packaged_settings`.
4. qwen did not corrupt or wrongly edit source: `git status --short` should show only
   the deterministic Stage 1 scaffold output (settings.py, urls.py, justfile, two
   headwind templates, plus new desktop_*.py and packaged_settings.py), the untracked
   `electron/` and `.stage/` dirs, and at most a `uv.lock` touched by `uv`. No other
   hand-edits from the model.
5. The qwen transcripts show qwen actually ran the verification commands and produced a
   coherent verification-only summary for each stage (it did not drift, loop, or
   corrupt files).

## Verdict

End your response with a clearly delimited verdict block:

```
VERDICT: PASS   (or FAIL)
REASON: <one or two sentences>
```

PASS only if qwen 3.6 27b drove the staged workflow to a working Electron-wrapped
django-resume (packaged smoke serving the app) without corrupting the repo. FAIL if
the packaged app does not run, the Electron scaffold is broken, or qwen corrupted
source files.

# Judge: did {{MODEL_DESC}} successfully wrap django-wiki in an Electron shell?

You are an independent **judge agent**. Do not be agreeable — verify everything
yourself with your bash/read tools before rendering a verdict.

## Context

A benchmark drove **{{MODEL_DESC}}** through the project's *staged* Electron-wrap
workflow on a clean clone of `django-wiki` (its `testproject` demo). The staged
workflow is:

- **Stage 1 (deterministic, NOT the model):** a scaffold script copies the Electron
  skeleton into `electron/` and writes the Django desktop baseline (packaged settings,
  desktop middleware, a runtime bootstrap that migrates an empty desktop DB and seeds
  a desktop superuser + the wiki root article, health + packaged static/media URL
  wiring, desktop auto-login).
- **Stage 2 (model):** verification-first Electron adaptation. A zero-edit pass is a
  valid success when the scaffold already covers the target.
- **Stage 3 (model):** verification-first Django integration. A zero-edit pass is a
  valid success when the scaffold already covers the target.

A verification-only zero-edit stage outcome is an accepted PASS, not a failure — the
same contract used for the django-resume benchmark.

## The wrapped clone to judge

`/Users/jochen/projects/django-wiki-clean`

## Evidence logs (read them)

- model Stage 2 transcript: `/tmp/wiki-stage2.log`
- model Stage 3 transcript: `/tmp/wiki-stage3.log`
- independent packaged smoke log: `/tmp/wiki-verify-smoke.log`

## What you must independently verify

1. The Electron shell scaffold is coherent in the clone:
   - `node --check electron/main.js` and `node --check electron/scripts/launch-electron.cjs`
   - `node --test electron/scripts/*.test.cjs` (should be all green)
   - `electron/wrap-target.json` describes django-wiki (not the starter)
2. The Django desktop integration is present (packaged settings, desktop middleware,
   runtime bootstrap with the wiki root-article seed, health/static/media URL wiring).
3. The packaged Electron app actually runs and serves the wiki. Run it yourself:
   `cd /Users/jochen/projects/django-wiki-clean && npm --prefix electron run smoke:packaged`
   Confirm the log shows `GET /health/` 200 and `GET /` 200 under
   `testproject.packaged_settings` (the wiki root article is served, not a login page).
4. The model did not corrupt or wrongly edit source: `git status --short` should show
   only the deterministic Stage 1 scaffold output (settings/base.py, urls.py, the new
   desktop_*.py and packaged_settings.py), the untracked `electron/` and `.stage/`
   dirs, and at most a `uv.lock` touched by `uv`. No other hand-edits from the model.
5. The model transcripts show it actually ran the verification commands and produced a
   coherent verification-only summary for each stage (no drift, loop, or corruption).

## Verdict

End your response with a clearly delimited verdict block:

```
VERDICT: PASS   (or FAIL)
REASON: <one or two sentences>
```

PASS only if the model drove the staged workflow to a working Electron-wrapped
django-wiki (packaged smoke serving the wiki root at `/` 200) without corrupting the
repo. FAIL if the packaged app does not serve, the Electron scaffold is broken, or the
model corrupted source files.

# Judge: did {{MODEL_DESC}} one-shot wrap django-resume in Electron?

You are an independent **judge agent**. Verify with your bash/read tools; do not be
agreeable.

## Context — this is the HARD one-shot variant

Unlike the staged benchmark (where a deterministic Stage 1 scaffold does the mechanical
wrapping and the model only verifies), this run gave the model the **original one-shot
prompt with NO scaffold**: the model had to author the *entire* Electron wrap from
scratch in one unattended agentic session — copy/adapt `electron/` (main.js,
package.json, builder config, preload, scripts, node tests), add desktop Django
integration (flat packaged settings, auto-auth middleware, packaged static serving,
health endpoint), and self-verify.

Historically this has only been passed by frontier models (Opus/Sonnet/gpt-5.4) in
8–21 minutes. Local/small models are expected to struggle.

## The result to judge

- Wrapped clone: `{{TGT}}`
- Model transcript: `{{LOG}}`
- Run summary: `{{SUMMARY}}` (read it for the harness's own pass/fail + timings)

## What to verify yourself

1. Did the model actually produce an Electron wrap? Check `{{TGT}}/electron/` exists
   with `main.js`, `package.json`, and scripts. Read `{{TGT}}` `git status`/diff to see
   what it authored (this is a large model-authored diff, not a scaffold).
2. Does it actually run? From `{{TGT}}`, try:
   `npm --prefix electron install && npm --prefix electron run smoke:packaged`
   (or whatever smoke/launch script the model created). A real PASS shows the packaged
   Django serving `/health/` 200 and the app root resolving to 200 (follow redirects).
3. If it FAILED, classify the failure mode from the transcript + repo state: e.g.
   incomplete `electron/` (never finished), drift/looping, context overflow, corrupted
   long file, broken packaged settings (404/500), or never started implementing.

## Verdict

End with:

```
VERDICT: PASS | FAIL | PARTIAL
FAILURE_MODE: <none, or a short classification if FAIL/PARTIAL>
REASON: <2-3 sentences citing what you ran and saw>
```

PASS only if the model authored a working Electron-wrapped django-resume (packaged
smoke serving the app). PARTIAL if it produced substantial correct structure but the
app does not fully serve. FAIL if it did not produce a working wrap.

# Final judge: was the one-shot django-resume benchmark run successful?

You are an independent **judge agent**. Verify with your bash/read tools; do not be
agreeable.

## What was attempted

The goal was to run the *harder* one-shot variant of the django-resume Electron-wrap
benchmark: instead of the staged workflow (deterministic Stage 1 scaffold + model just
verifies), the model is given the **original one-shot prompt with NO scaffold** and must
author the entire wrap from scratch in one unattended agentic session
(`skills/wrap-existing-django-in-electron/prompt.md`). Then verify + judge.

"Benchmark run successful" here does **NOT** require that local models pass. It means:
the benchmark was actually conducted and produced **valid, documented evidence** — in
particular, the harness is proven correct by a control that DOES pass (so any local
failures are real model results, not harness bugs), and each cell's outcome is backed by
artifacts.

## Cells run (results under `.bench-qwen36/`)

| Result dir | Engine / model | Budget | Recorded outcome |
|---|---|---|---|
| `results-oneshot-control-gpt55/` | openai-codex gpt-5.5 (frontier control) | ~7 min | PASS |
| `results-oneshot-llamacpp/`      | llama.cpp / qwen 3.6 27b (32k ctx)     | killed at 37 min | FAIL (1 partial Django file, no electron/; ~25k/32k context pressure; killed before overflow) |
| `results-oneshot-ds4/`           | ds4.c / DeepSeek V4 Flash (128k ctx)   | 50 min cap | FAIL (skeleton then stall) |
| `results-oneshot-ds4-2h/`        | ds4.c / DeepSeek V4 Flash (128k ctx)   | 2h budget  | FAIL (explored 18 read+47 bash, 0 writes, exited cleanly with no wrap; the shared 128k server session overflowed — not per-run attributable to this run's own transcript) |
| `results-oneshot-ds4-4h/`        | ds4.c / DeepSeek V4 Flash (128k ctx)   | 4h budget  | FAIL (context overflow; `500 prompt exceeds context`) |
| `results-oneshot-ds4-256k/`      | ds4.c / DeepSeek V4 Flash (256k ctx)   | 2h budget  | FAIL (no overflow, reached ~132k; 122 bash + 1 write, then `finish=error "invalid tool call"` emitting a large settings write) |

## What you must independently verify

1. **The control genuinely passed** (this validates the harness). From the control
   clone `/Users/jochen/projects/django-resume-oneshot-control`, run:
   `npm --prefix electron install && npm --prefix electron run smoke:packaged`
   Confirm `GET /health/` 200 and the app root resolving to 200 (follow redirects). Also
   confirm the wrap was MODEL-authored (large diff in `results-oneshot-control-gpt55/diff-stat.txt`),
   not a scaffold.
2. **The local failures are real, with evidence.** Read each FAIL summary.txt; spot-check
   that the local cells did NOT produce a working wrap (no `electron/main.js`, smoke not
   served). The ds4 json transcripts (`oneshot.log`) record the tool usage — confirm ds4
   explored (read/bash) but did not author the wrap and self-terminated well within its
   budget (so more time would not help).
3. **Coverage is sufficient to support the conclusion.** Two local models (qwen 3.6 27b
   and DeepSeek V4 Flash) attempted; a frontier control passed; ds4 given escalating
   time budgets (50min→2h→4h) AND escalating context (128k→256k). The corrected,
   artifact-supported conclusion is:
   - Frontier (gpt-5.5, 272k ctx) one-shots the wrap in ~7 min.
   - **qwen 3.6 27b** did not converge: after 37 min it had authored only 1 partial
     Django middleware and no `electron/` shell, under heavy **32k** context pressure
     (reached ~25k after reading the 505-line skill + architecture + spec). It was
     stopped (SIGTERM) at 37 min to free RAM for ds4 — before its 40-min cap and before
     a definitive 32k overflow — so this cell shows non-convergence, not a proven
     overflow.
   - **DeepSeek V4 Flash** fails by overflowing **128k** context in the 2h/4h runs
     (it self-terminated well within those time budgets, so *time* was not the limiter —
     *context* was). Given **256k** headroom it no longer overflowed (reached ~132k) but
     still failed: after 122 exploration commands it emitted a **malformed/invalid tool
     call** while trying to write a large settings file.
   - So local one-shot failure is driven by **context exhaustion at smaller windows AND
     unreliable large-file tool-call emission even with ample context** — not by wall
     time. This is consistent with the staged workflow existing precisely because the
     one-shot prompt is too large for smaller local models.

   Confirm this conclusion matches what the artifacts actually show (check the ds4
   transcripts for the context-overflow errors at 128k and the `invalid tool call` at
   256k).

## Verdict

End with:

```
BENCHMARK_RUN_SUCCESSFUL: YES | NO
REASON: <2-4 sentences: did the harness work (control pass verified), are the local
failures real and evidenced, and is the conclusion supported?>
```

Answer YES only if you independently confirmed the control's working wrap, the local
failures are genuine (not harness artifacts), and the evidence supports the stated
conclusion.

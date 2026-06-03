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
| `results-oneshot-llamacpp/`      | llama.cpp / qwen 3.6 27b (**32k, under-provisioned**) | killed at 37 min | FAIL (1 partial Django file, no electron/; ~24k/32k; killed before overflow). NB: the model is trained for 256k — this run under-served it; see the 256k row below |
| `results-oneshot-qwen256k/`      | llama.cpp / qwen 3.6 27b (**256k**, full trained ctx) | 79 min (completed) | **PARTIAL** (authored a near-complete wrap: 30 source files, Electron node tests pass; packaged smoke FAILED on `ModuleNotFoundError: No module named 'core'`) |
| `results-oneshot-ds4/`           | ds4.c / DeepSeek V4 Flash (128k ctx)   | 50 min cap | FAIL (skeleton then stall) |
| `results-oneshot-ds4-2h/`        | ds4.c / DeepSeek V4 Flash (128k ctx)   | 2h budget  | FAIL (explored 18 read+47 bash, 0 writes, exited cleanly with no wrap; the shared 128k server session overflowed — not per-run attributable to this run's own transcript) |
| `results-oneshot-ds4-4h/`        | ds4.c / DeepSeek V4 Flash (128k ctx)   | 4h budget  | FAIL (context overflow; `500 prompt exceeds context`) |
| `results-oneshot-ds4-256k/`      | ds4.c / DeepSeek V4 Flash (256k ctx)   | 2h budget  | FAIL (no overflow, reached ~132k; 122 bash + 1 write, then `finish=error "invalid tool call"` emitting a large settings write) |

## What you must independently verify

NOTE: the disposable target clones and the multi-GB raw json transcripts have been
removed/gitignored. Judge from the committed per-cell artifacts under
`.bench-qwen36/results-oneshot-*/`: `summary.txt`, `diff-stat.txt`,
`transcript-summary.txt`, `verify-smoke.log`, and `server-evidence` files.

1. **The control genuinely passed** (this validates the harness). Read
   `results-oneshot-control-gpt55/summary.txt` (`outcome=PASS`, smoke health 200, root
   served) and `diff-stat.txt` (a large MODEL-authored wrap, package-lock excluded), and
   `verify-smoke.log` (`GET /health/` 200 and `/resume/` 200). (An earlier judge run
   re-ran the control's packaged smoke live and confirmed it served; that clone is now
   removed.)
2. **The local results are real, with evidence.** Read each `summary.txt`; confirm the
   FAIL/PARTIAL cells did not produce a clean serving PASS. The `transcript-summary.txt`
   files record tool usage; `server-evidence` files record the ds4 context/tool-call
   errors. For **qwen256k specifically**, confirm: `outcome=FAIL (PARTIAL...)`,
   `node_tests=pass`, 30 model-authored source files in `diff-stat.txt`, and
   `verify-smoke.log` showing the packaged smoke failed with
   `ModuleNotFoundError: No module named 'core'`.
3. **Coverage is sufficient to support the conclusion.** Two local models (qwen 3.6 27b
   and DeepSeek V4 Flash) attempted; a frontier control passed; ds4 given escalating
   time budgets (50min→2h→4h) AND escalating context (128k→256k). The corrected,
   artifact-supported conclusion is:
   - Frontier (gpt-5.5, 272k ctx) produced a clean PASS in ~7 min.
   - **qwen 3.6 27b — context was the dominant limiter, partly a serving artifact.** At
     32k (1/8th of its trained 256k window) it authored only a partial Django file and no
     `electron/` shell before being stopped. Re-served at its **full 256k** context and
     run to completion (79 min), it authored a **near-complete wrap** — 30 source files,
     Electron node tests passing — and failed only the packaged smoke on a single `core`
     module-path bug (a **PARTIAL**). So the 32k failure was largely under-provisioning,
     not a hard model limit.
   - **DeepSeek V4 Flash** fails by overflowing **128k** context in the 2h/4h runs
     (it self-terminated well within those time budgets, so *time* was not the limiter —
     *context* was). Given **256k** headroom it no longer overflowed (reached ~132k) but
     still failed: after 122 exploration commands it emitted a **malformed/invalid tool
     call** while trying to write a large settings file.
   - So the honest conclusion is **context-window provisioning and large-write tool-call
     reliability are decisive for local one-shot** — not wall time. Given its full
     trained context, a local 27B (qwen) gets *most of the way* through a one-shot wrap;
     a frontier model finishes cleanly and far faster. This is consistent with the staged
     workflow existing precisely for the "one-shot prompt too large / smaller context
     window" regime. Do NOT accept a conclusion that flatly says local models cannot
     one-shot a wrap.

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

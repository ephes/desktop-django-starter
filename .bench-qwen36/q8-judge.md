# Judge: did the Q8_0 quant experiment add a sound, evidenced result?

You are an independent **judge agent**. Verify with your bash/read tools from the repo
`/Users/jochen/projects/desktop-django-starter`. Do not be agreeable.

## What was attempted

The best local one-shot config (qwen 3.6 27b **dense**, 256k ctx, thinking OFF) had
produced a PARTIAL at **Q4_K_M** (run 24b: near-complete wrap, node tests pass, packaged
smoke failed on `ModuleNotFoundError: No module named 'core'`). The question was whether a
**higher-precision quant** closes the gap. So the identical config was re-run at
near-lossless **Q8_0** (26.6 GB GGUF) to isolate the quant variable. Result dir:
`.bench-qwen36/results-oneshot-qwen-q8-q8/`.

## Verify independently

1. **The Q8 run is real and completed.** Read `results-oneshot-qwen-q8-q8/summary.txt`
   and `transcript-summary.txt`: confirm `pi_exit=0`, thinking=off, `node_tests=pass`
   (51/51), ~31 model-authored files, and that the run reached `agent_end` (not killed).
2. **The smoke genuinely failed and why.** Read `verify-smoke.log` and
   `verify-smoke-gpufree.log`. Confirm: `stage-backend` succeeded ("core ready!", static
   files copied, bundle staged) but the packaged smoke timed out and never logged a
   `GET /health/ ... 200`. Confirm the documented root cause is plausible: the model's
   `main.js` `validatePackagedBackendRoot()` requires `manage.py` at the backend ROOT and
   `buildManageInvocation()` runs it from `cwd=backendRoot`, while the staged bundle has
   `manage.py` only under `example/` (the clone is deleted, but `diff-stat.txt` /
   transcript-summary should support this). Confirm the GPU/network "exit_code=15" lines
   are teardown at the 200 s timeout, NOT the cause — evidenced by the GPU-free re-run
   reproducing the identical timeout.
3. **The comparison and conclusion are honest.** The claim is: **Q8_0 did not close the
   gap** — both Q4_K_M-off and Q8_0-off are the same PARTIAL tier (near-complete wrap, all
   node tests pass, packaged smoke fails on one self-authored path/module contract; the
   specific bug merely moved). Therefore quantization is not the bottleneck and bf16 would
   likely behave the same. Check this against `RUNTIME-COMPARISON.md` (one-shot table Q8
   row + the quant takeaway bullet) and `run-log.md` (row 24f). Flag any overclaim.

## Verdict

End with exactly:

```
Q8_EXPERIMENT_SOUND: YES | NO
REASON: <2-4 sentences: is the Q8 cell real and evidenced, is the smoke-failure root
cause correctly attributed (not GPU contention), and is the "quant did not close the gap"
conclusion supported without overclaiming?>
```

Answer YES only if you independently confirmed the artifacts and the conclusion is
supported by them.

# One-shot django-resume benchmark — pi judge verdicts (openai-codex/gpt-5.5)

## Benchmark-success judge (final, corrected-conclusion re-run)
```
BENCHMARK_RUN_SUCCESSFUL: YES
REASON: I verified the frontier control by rerunning `npm --prefix electron install && npm --prefix electron run smoke:packaged`; `/health/` returned 200 and `/` redirected to `/resume/` which returned 200, and the control diff shows a large model-authored Electron/Django wrap from a source repo with no preexisting `electron/`. The local result artifacts show genuine failures: incomplete/no `electron/main.js`, failed/no smoke serving, ds4 128k runs ending with KV/context errors (`Metal graph compressed KV cache capacity exceeded`, `500 prompt exceeds context`), and the 256k run reaching ~133k tokens before `invalid tool call` while attempting a large write. Coverage is sufficient: qwen 32k plus ds4 at 128k/256k with escalating time budgets, with failures attributable to context/tool-call reliability rather than a bad harness.
```

## First-pass benchmark judge (flagged my overclaim — NO)
```
BENCHMARK_RUN_SUCCESSFUL: NO
REASON: I independently verified the control works: packaged smoke returns `/health/` 200 and `/` redirects to `/resume/` 200, and the control diff is a large model-authored wrap. The local failures are genuine: qwen produced no Electron wrap, ds4 smoke failed or produced no `electron/main.js`, and ds4 transcripts show read/bash exploration with 0 writes in the longer runs. However, the stated conclusion is not fully supported: ds4-4h ends with `500 prompt exceeds context`, and ds4-2h ends in a provider error around 130k tokens, so the claim that ds4 failed “not time or context” is contradicted by the artifacts.
```

## Benchmark-success judge — updated to include the qwen256k cell (2026-06-03)
```
BENCHMARK_RUN_SUCCESSFUL: YES
REASON: The control artifacts verify the harness: PASS outcome, 35-file model-authored wrap, node tests passing, and packaged smoke serving `/health/` 200 plus `/` → `/resume/` 200. The local outcomes are genuine non-passes: qwen32 produced only one Django file/no Electron, qwen256k produced a 30-file partial with node tests passing but smoke failing on `ModuleNotFoundError: No module named 'core'`, and ds4 runs show no clean serving pass with 128k context-overflow evidence and 256k `invalid tool call` evidence. The supported conclusion is the nuanced one: context provisioning and tool-call reliability dominate local one-shot behavior; full-context qwen gets close, while the frontier control finishes cleanly.
```

## Q8_0 quant experiment (run 24f) — 2026-06-03

`Q8_EXPERIMENT_SOUND: YES` (pi / openai-codex/gpt-5.5, independent).
REASON: The Q8 cell is real and evidenced (`pi_exit=0`, thinking off, clean `agent_end`,
~31 authored files, Node tests 51/51 pass). The packaged smoke failure is consistently a
timeout after successful backend staging with no `/health/` 200; the GPU/network
`exit_code=15` lines are teardown (the GPU-free rerun reproduces the same timeout). The
"Q8 did not close the gap" conclusion is supported; the bf16 statement is framed as a
likely/near-lossless extrapolation, not a measured result.

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

# Wrapping Skill Run Log

Target: django-resume | Agent: Claude Code (Opus 4.6) | Mode: unattended (`claude -p`)

| Run | Date | Duration | Tier | Tests | Smoke | Root URL | Node tests | Ref | Notes |
|-----|------|----------|------|-------|-------|----------|------------|-----|-------|
| 1 | 2026-04-03 | 17m 04s | partial | 95/95 | pass | 404 | missing | `14c89da` | settings package broke packaged mode; window loaded 404; no node tests |
| 2 | 2026-04-03 | 10m 08s | Tier 1 | 95/95 | pass | 302 | 20/20 | `c9ba37e` | flat settings, root redirect, node tests — all 3 bugs fixed, 7min faster |
| 3 | 2026-04-04 | 13m 39s | Tier 1+ | 95/95 | pass | 302→200 | 20/20 | `658ca3e` | packaged static serving, landing resolves to 200, auth URLs, adapted test assertions |

## How to read this

- **Ref** is the commit on the starter repo used for that run.
- To see what changed between runs: `git diff <ref1>..<ref2> -- skills/`
- To see the full skill at a point in time: `git show <ref>:skills/wrap-existing-django-in-electron/SKILL.md`

## How to add a row after a run

After completing a wrapping run (successful or not), add a row to the table above
and commit it to the starter repo. Use this workflow:

```bash
# 1. Get the starter ref that was used for the run
git -C ~/projects/desktop-django-starter rev-parse --short HEAD

# 2. Collect results from the agent's output:
#    - Duration: from the `time` wrapper
#    - Tier: "partial" if any verification failed, "Tier 1" if all 4 checks pass,
#      "Tier 2" if desktop-stage and desktop-smoke also pass
#    - Tests: number passing (e.g., "95/95")
#    - Smoke: "pass" or "fail" (just desktop-dev-smoke)
#    - Root URL: HTTP status of GET / (200, 302, or 404)
#    - Node tests: number passing (e.g., "20/20") or "missing"
#    - Notes: brief description of what happened, especially failures

# 3. Edit this file — append one row to the table

# 4. Commit
cd ~/projects/desktop-django-starter
git add skills/wrap-existing-django-in-electron/run-log.md
git commit -m "Record wrapping run N results"
```

**For agents recording their own run:** If you just completed a wrapping run and are
asked to record the results, read this file, append a row with the data from your
run, and commit. Use the next sequential run number. Keep notes concise (under 100 chars).

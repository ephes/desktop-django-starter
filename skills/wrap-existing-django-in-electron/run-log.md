# Wrapping Skill Run Log

Targets: django-resume, django-wiki, django-cast | Mode: unattended | Agents: Claude Code (Opus/Sonnet), Codex (gpt-5.4), pi (Opus, Sonnet, gpt-5.4)

| Run | Date | Duration | Tier | Tests | Smoke | Root URL | Node tests | Ref | Notes |
|-----|------|----------|------|-------|-------|----------|------------|-----|-------|
| 1 | 2026-04-03 | 17m 04s | partial | 95/95 | pass | 404 | missing | `14c89da` | settings package broke packaged mode; window loaded 404; no node tests |
| 2 | 2026-04-03 | 10m 08s | Tier 1 | 95/95 | pass | 302 | 20/20 | `c9ba37e` | flat settings, root redirect, node tests — all 3 bugs fixed, 7min faster |
| 3 | 2026-04-04 | 13m 39s | Tier 1+ | 95/95 | pass | 302→200 | 20/20 | `658ca3e` | packaged static serving, landing resolves to 200, auth URLs, adapted test assertions |
| 4 | 2026-04-04 | 13m 14s | Tier 1 | 95/95 | pass | 302→200 | pass | `d2b55d6` | auto-login middleware instead of auth infra, clean origin/main run (no manual sync) |
| 5 | 2026-04-04 | 13m 00s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `e805fbd` | preserved existing auth/data/root redirect, ran just check not just pytest |
| 6 | 2026-04-04 | 13m 07s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `1ea668c` | auto-auth middleware, no login page, desktop_settings.py for dev mode, 17KB content |
| 7a | 2026-04-04 | 4m 51s | fail | — | — | — | — | `56237ed` | Sonnet: presented plan, asked for confirmation, never implemented. Fixed prompt. |
| 7b | 2026-04-04 | 13m 43s | Tier 1 | 125/125 | pass | pass | pass | `3663262` | Sonnet: all checks pass, light bg, auto-auth as 'user', flat settings, no login page |
| 8 | 2026-04-04 | 15m 39s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `0beb612` | Sonnet: nav menu (Back/Forward/Resume List), setWindowOpenHandler, platform shortcuts, auto-auth |
| 9 | 2026-04-04 | 18m 40s | Tier 1 | pass | pass | 302→200 | pass | `0beb612` | Codex (gpt-5.4): nav menu, setWindowOpenHandler, seed-data copy, desktop runtime tests, docs updates |
| 10 | 2026-04-05 | 8m 08s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `49b5cae` | pi (Opus): fastest run, Go menu, env-gated auto-auth, seed-db copy, retro included |
| 11 | 2026-04-05 | 16m 07s | Tier 1 | pass | pass | 302→200 | pass | `9a98b7c` | pi (gpt-5.4): nav menu, seed-db copy, CI workflow, checksum helper, retro included |
| 12 | 2026-04-05 | 14m 10s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `a5da82d` | pi (Sonnet): Go menu, env-gated auto-auth, seed-db copy, installable library wheel noted |
| 13 | 2026-04-06 | 13m 17s | Tier 1 | 289/289 | pass | 200 | 20/20 | `0f15e85` | **django-wiki** · pi (Opus): first new target, Go menu, flat settings beside settings package, fixture loading, wiki wheel in staging |
| 14 | 2026-04-06 | 20m 50s | Tier 1 | pass | pass | 200 | pass | `e46b200` | **django-wiki** · pi (Sonnet): auto-auth as admin, catch-all URL ordering, seed-db copy, no splash, retro included |
| 15 | 2026-04-06 | 16m 56s | Tier 1 | 1098/1098 | pass | 200 | 16/16 | `93ab020` | **django-cast** · pi (Opus): Wagtail CMS, settings package, manage.py setdefault fix, seed via mgmt command |
| 16 | 2026-04-06 | 15m 00s | Tier 1 | pass | pass | 200 | 20/20 | `590190d` | **django-cast** · pi (Sonnet): CMS/Admin menu items, same-origin window handling, manage.py setdefault fix |
| 17 | 2026-04-06 | — | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `42e0c34` | First `scripts/wrap --run` test from /tmp/ clone. Review: missing entitlements, no testserver, dirtied db.sqlite3 |
| 18 | 2026-04-07 | 14m 33s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `998d2f3` | pi (gpt-5.4): `dds wrap` path, skill v2, 6/6 checks, but review found seed media not bootstrapped (404) |
| 19 | 2026-04-07 | 17m 47s | Tier 1 | 125/125 | pass | 302→200 | 20/20 | `66b9aa7` | pi (gpt-5.4): skill v3 with media fix, 6/6 checks + media probe pass, review clean except upgrade-path edge |
| 20 | 2026-04-08 | 14m 53s | Tier 1 | pass | pass | 302→200 | pass | `b22c03a` | pi (gpt-5.4): skill v4, clean-install media 200, but upgrade-path probe 404 (bare exists guard, no CI) |

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

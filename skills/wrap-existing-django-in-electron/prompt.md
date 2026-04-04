# Wrap this Django project in an Electron shell

Read the wrapping skill and reference material from the desktop-django-starter repo:

1. Read `../desktop-django-starter/skills/wrap-existing-django-in-electron/SKILL.md` — this is your workflow.
2. Read `../desktop-django-starter/docs/architecture.md` — this is the runtime contract.
3. Use the starter's `shells/electron/` and `scripts/` directories as reference code to copy and adapt.

Apply the skill to this Django project (the current working directory). Follow the
skill's "Strategy: Copy and Adapt" section: copy the starter's Electron files into
this project's `electron/` directory, then adapt them to this project's structure.

Implement directly. Do not present a plan or ask for confirmation — this is an
unattended run with no human in the loop.

Critical points — read the skill carefully on these:
- Use flat settings files (base_settings.py, packaged_settings.py), NOT a settings package.
- The desktop app must never show a login page. The user opens the app and sees their content immediately. If the Django project has views behind `@login_required`, add a small middleware to desktop settings (both dev and packaged) that silently authenticates every request as the project's existing user — so `request.user` is real and all data shows up. Do NOT create new user accounts, do NOT add login templates or auth URLs. Preserve existing users and data. The full redirect chain from `/` must end at a 200 with real content visible.
- Packaged mode (DEBUG=False) needs explicit static file serving in the URLconf. Without this, CSS/JS/images return 404 in the packaged app.
- Copy and adapt the starter's Node test harness (*.test.cjs files). Update assertions to match this project's values (settingsModule, appId, etc.).
- Assess what the app loses when browser chrome disappears (back/forward, address bar, tabs). Restore only the missing affordances the app actually needs — via Electron menu, Django template override, or nothing if the app already navigates well on its own.

When done, verify (see Self-Verification in the skill for details):
1. The existing test suite still passes.
2. `just desktop-dev-smoke` passes (boots Electron, health check responds 200, exits cleanly).
3. The URL Electron loads resolves to a 200 (follow full redirect chain, no 404 at any step).
4. `npm --prefix electron test` passes.

If any verification step fails, report what failed clearly and exit non-zero.

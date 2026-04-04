# Wrap this Django project in an Electron shell

Read the wrapping skill and reference material from the desktop-django-starter repo:

1. Read `../desktop-django-starter/skills/wrap-existing-django-in-electron/SKILL.md` — this is your workflow.
2. Read `../desktop-django-starter/docs/architecture.md` — this is the runtime contract.
3. Use the starter's `shells/electron/` and `scripts/` directories as reference code to copy and adapt.

Apply the skill to this Django project (the current working directory). Follow the
skill's "Strategy: Copy and Adapt" section: copy the starter's Electron files into
this project's `electron/` directory, then adapt them to this project's structure.

Critical points — read the skill carefully on these:
- Use flat settings files (base_settings.py, packaged_settings.py), NOT a settings package.
- The Electron window must land on real app content. Do NOT create new user accounts, auto-login middleware, or auth flows — preserve the project's existing users, data, and login configuration. If the project already has a root redirect and login URL, just keep them. Follow the full redirect chain — the final response must be 200.
- Packaged mode (DEBUG=False) needs explicit static file serving in the URLconf. Without this, CSS/JS/images return 404 in the packaged app.
- Copy and adapt the starter's Node test harness (*.test.cjs files). Update assertions to match this project's values (settingsModule, appId, etc.).

When done, verify (see Self-Verification in the skill for details):
1. The existing test suite still passes.
2. `just desktop-dev-smoke` passes (boots Electron, health check responds 200, exits cleanly).
3. The URL Electron loads resolves to a 200 (follow full redirect chain, no 404 at any step).
4. `npm --prefix electron test` passes.

If any verification step fails, report what failed clearly and exit non-zero.

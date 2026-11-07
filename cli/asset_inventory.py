"""Canonical files required in staged CLI distributions (no CLI imports)."""

# Repo-relative paths to bundle.  The _assets layout mirrors the repo structure
# so prompt.md path substitution (replacing "../desktop-django-starter/" with the
# assets root) works unchanged.
CANONICAL_ASSETS: list[str] = [
    # Electron shell
    "shells/electron/main.js",
    "shells/electron/preload.cjs",
    "shells/electron/package.json",
    "shells/electron/electron-builder.config.cjs",
    "shells/electron/scripts/launch-electron.cjs",
    "shells/electron/scripts/bundled-python.cjs",
    "shells/electron/scripts/electron-builder-config.cjs",
    "shells/electron/scripts/auth-token.cjs",
    "shells/electron/scripts/materialize-symlinks.cjs",
    "shells/electron/scripts/window-guards.cjs",
    "shells/electron/scripts/process-exit-policy.cjs",
    "shells/electron/scripts/updates.cjs",
    "shells/electron/scripts/orphan-processes.cjs",
    "shells/electron/scripts/quit-guard.cjs",
    "shells/electron/scripts/bundled-python.test.cjs",
    "shells/electron/scripts/electron-builder-config.test.cjs",
    "shells/electron/scripts/auth-token.test.cjs",
    "shells/electron/scripts/materialize-symlinks.test.cjs",
    "shells/electron/scripts/window-guards.test.cjs",
    "shells/electron/scripts/process-exit-policy.test.cjs",
    "shells/electron/scripts/updates.test.cjs",
    # Signing entitlements
    "shells/electron/signing/entitlements.mac.plist",
    "shells/electron/signing/entitlements.mac.inherit.plist",
    # Icon assets
    "shells/electron/assets/icons/app-icon.png",
    "shells/electron/assets/icons/app-icon.icns",
    # Shared packaging scripts
    "scripts/stage-backend.cjs",
    "scripts/bundled-python.cjs",
    "scripts/materialize-symlinks.cjs",
    "scripts/prune-bundled-python-runtime.cjs",
    "scripts/desktop_process_guard.py",
    # Wrapping skill and prompt
    "skills/wrap-existing-django-in-electron/SKILL.md",
    "skills/wrap-existing-django-in-electron/prompt.md",
    # Documentation
    "docs/architecture.md",
    "docs/specification.md",
    "docs/decisions.md",
    "docs/agent-use.md",
    "llms.txt",
    # CI workflow template
    ".github/workflows/desktop-packages.yml",
]

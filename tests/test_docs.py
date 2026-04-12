from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_docs_scaffold_exists() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "llms.txt",
        ROOT / ".readthedocs.yml",
        ROOT / "justfile",
        ROOT / "pyproject.toml",
        ROOT / "assets" / "brand" / "flying-stable-app-icon.svg",
        ROOT / "docs" / "conf.py",
        ROOT / "docs" / "index.md",
        ROOT / "docs" / "llms.txt",
        ROOT / "docs" / "specification.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "decisions.md",
        ROOT / "docs" / "release.md",
        ROOT / "docs" / "backlog.md",
        ROOT / "docs" / "done.md",
        ROOT / "docs" / "agent-use.md",
        ROOT / "docs" / "shells" / "electron.md",
        ROOT / "docs" / "shells" / "tauri.md",
        ROOT / "docs" / "shells" / "positron.md",
        ROOT / "scripts" / "stage-backend.cjs",
        ROOT / "scripts" / "write-checksums.py",
        ROOT / "shells" / "electron" / "package.json",
        ROOT / "shells" / "electron" / "scripts" / "materialize-symlinks.cjs",
        ROOT / "shells" / "tauri" / "package.json",
        ROOT / "shells" / "tauri" / "src-tauri" / "tauri.conf.json",
        ROOT / "shells" / "positron" / "pyproject.toml",
        ROOT / "skills" / "wrap-existing-django-in-electron" / "SKILL.md",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "workflows" / "desktop-packages.yml",
        ROOT / ".github" / "workflows" / "tauri-packages.yml",
    ]
    for path in expected:
        assert path.exists(), f"Missing expected file: {path}"


def test_docs_index_references_main_pages() -> None:
    index = (ROOT / "docs" / "index.md").read_text()
    assert "specification" in index
    assert "architecture" in index
    assert "decisions" in index
    assert "release" in index
    assert "backlog" in index
    assert "done" in index
    assert "agent-use" in index
    assert "shells/electron" in index
    assert "shells/tauri" in index
    assert "shells/positron" in index
    assert "Design Guide <design-guide>" in index
    assert "Tasks Demo Design <superpowers/specs/2026-03-30-tasks-demo-frontend-design>" in index
    assert "multi-shell-plan" not in index
    assert "branch-integration-plan" not in index
    assert not (ROOT / "docs" / "multi-shell-plan.md").exists()
    assert not (ROOT / "docs" / "branch-integration-plan.md").exists()


def test_ci_workflow_covers_root_cli_and_electron_validation() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "actions/setup-node@v5" in workflow
    assert "shells/electron/package-lock.json" in workflow
    assert "npm --prefix shells/electron ci" in workflow
    assert "npm --prefix shells/electron test" in workflow
    assert "uv run python cli/sync_assets.py" in workflow
    assert "working-directory: cli" in workflow
    assert "uv run --with pytest python -m pytest tests/" in workflow
    assert "npm --prefix shells/electron test" in readme
    assert "just cli-test" in readme


def test_release_docs_cover_signing_and_manual_updates() -> None:
    readme = (ROOT / "README.md").read_text()
    release = (ROOT / "docs" / "release.md").read_text()
    architecture = (ROOT / "docs" / "architecture.md").read_text()
    specification = (ROOT / "docs" / "specification.md").read_text()
    llms = (ROOT / "llms.txt").read_text()
    docs_llms = (ROOT / "docs" / "llms.txt").read_text()
    backlog = (ROOT / "docs" / "backlog.md").read_text()
    done = (ROOT / "docs" / "done.md").read_text()
    tauri_doc = (ROOT / "docs" / "shells" / "tauri.md").read_text()
    positron_doc = (ROOT / "docs" / "shells" / "positron.md").read_text()
    electron_doc = (ROOT / "docs" / "shells" / "electron.md").read_text()
    gitignore = (ROOT / ".gitignore").read_text()

    assert "docs/release.md" in readme
    assert "docs/backlog.md" in readme
    assert "docs/done.md" in readme
    assert "SHA-256" in readme
    assert ".stage/backend" in readme
    assert "shells/electron" in readme
    assert "shells/tauri" in readme
    assert "shells/positron" in readme
    assert "assets/brand/flying-stable-app-icon.svg" in readme
    assert "kept in the repo" in readme
    assert "just tauri-start" in readme
    assert "just tauri-build" in readme
    assert "`nsis` on Windows" in readme
    assert "real live Windows machine" in readme
    assert "minimal CSP" in readme
    assert "not a release-parity path" in readme
    assert "just positron-start" in readme
    assert "just positron-package-dmg" in readme
    assert "dist/github-actions/latest" in readme
    assert "dist/github-actions/tauri/latest" in readme
    assert "per-session shell-to-Django auth token" in readme
    assert "the shells now add a per-session shell-to-Django auth token" in readme
    assert "Tauri and Positron pass the same setting to Django" in readme
    assert "HttpOnly same-origin cookie" in readme
    assert "taskkill /t /f" in readme
    assert "transaction_mode=IMMEDIATE" in readme
    assert "APPLE_API_KEY_ID" in release
    assert "WIN_CSC_LINK" in release
    assert "shells/electron/signing/" in release
    assert "just tauri-build" in release
    assert "tauri-packages.yml" in release
    assert "official-style `tauri-action`" in release
    assert "build-only mode" in release
    assert "desktop-django-starter-tauri-windows-sha256.txt" in release
    assert "downloadBootstrapper" in release
    assert "real live Windows machine test" in release
    assert "Windows NSIS validation checklist" in release
    assert "minimal CSP" in release
    assert "no dedicated Positron GitHub packaging workflow" in release
    assert "just positron-package-dmg" in release
    assert "not a release-parity path in this slice" in release
    assert "air-gapped" in release
    assert "app.sqlite3" in release
    assert "auto-update" in release
    assert "desktop-django-starter-macos-sha256.txt" in release
    assert "desktop-django-starter-windows-sha256.txt" in release
    assert "promote both files together" in release
    assert "Linux verification" in release
    assert "GITHUB_REPOSITORY" in readme
    assert "published GitHub releases" in readme
    assert "local `origin` Git remote" in release
    assert "draft release is useful for staging or review" in release
    assert "per-session shell-to-Django auth token" in release
    assert "Electron now adds a per-session shell-to-Django auth token" in release
    assert "Tauri and Positron now add comparable per-session shell-to-Django" in release
    assert "taskkill /t /f" in release
    assert "transaction_mode=IMMEDIATE" in release
    assert "assets/brand/" in architecture
    assert ".stage/backend/" in architecture
    assert "shells/electron/" in architecture
    assert "shells/tauri/" in architecture
    assert "shells/positron/" in architecture
    assert "cli/" in architecture
    assert "skills/" in architecture
    assert "tasks_demo/" in architecture
    assert "shells/electron/" in docs_llms
    assert "assets/brand/" in docs_llms
    assert "scripts/wrap" in docs_llms
    assert "skills/wrap-existing-django-in-electron/SKILL.md" in docs_llms
    assert "design-guide.html" in docs_llms
    assert "packaged-app copy first" in architecture
    assert "shell-local splash window" in architecture
    assert "The current implementation follows this sequence" in architecture
    expected = "fallback `DJANGO_SECRET_KEY` only when the environment does not provide one"
    assert expected in architecture
    assert "per-session shell-to-Django auth token" in architecture
    assert "Tauri and Positron use the same Django token setting" in architecture
    assert "taskkill /t /f" in architecture
    assert "PRAGMA journal_mode=WAL;" in architecture
    assert "per-session shell-to-Django auth token" in specification
    assert "not a CSRF replacement" in specification
    assert "comparison paths in this repo" in specification
    assert "shells/electron/" in llms
    assert "shells/tauri/" in llms
    assert "shells/positron/" in llms
    assert "assets/brand/" in llms
    assert "GitHub-hosted Tauri artifact workflow" in llms
    assert "prepared, unverified Windows NSIS path" in llms
    assert "minimal localhost-aware CSP" in llms
    assert "per-session shell-to-Django auth token" in llms
    assert "Tauri and Positron pass the same setting to Django" in llms
    assert "taskkill /t /f" in llms
    assert "transaction_mode=IMMEDIATE" in llms
    assert "shells/electron.html" in docs_llms
    assert "shells/tauri.html" in docs_llms
    assert "shells/positron.html" in docs_llms
    assert "backlog.html" in docs_llms
    assert "done.html" in docs_llms
    assert "BL-005: Documentation Consistency and Discoverability Cleanup" not in backlog
    assert "BL-005: Documentation Consistency and Discoverability Cleanup" in done
    assert "BL-006: Electron Navigation and Window Hardening" not in backlog
    assert "BL-006: Electron Navigation and Window Hardening" in done
    assert "BL-007: Experimental Shell Lifecycle and Runtime Clarity" not in backlog
    assert "BL-007: Experimental Shell Lifecycle and Runtime Clarity" in done
    assert "BL-004: CI Validation Coverage for Electron and CLI" not in backlog
    assert "BL-004: CI Validation Coverage for Electron and CLI" in done
    assert "BL-002: Tauri Connected Auto-Update" in backlog
    assert "tauri-plugin-updater" in backlog
    assert "BL-003: Positron Update Strategy and Auto-Update Path" in backlog
    assert (
        "Briefcase's development update workflow is not the same thing as an end-user auto-updater"
        in backlog
    )
    assert "implementation handoff" in backlog
    assert "done.md" in backlog
    assert "BL-001: Electron Connected Auto-Update" not in backlog
    assert "BL-001: Electron Connected Auto-Update" in done
    assert "electron-updater" in done
    assert "Help > Check for Updates..." in done
    assert "publish_release=true" in done
    assert "app.security.csp" in tauri_doc
    assert "Current minimal CSP posture" in tauri_doc
    assert "canonical written checklist" in tauri_doc
    assert "not a release-parity path in this slice" in tauri_doc
    assert "SIGTERM" in tauri_doc
    assert "2-second grace period" in tauri_doc
    assert "deny child-window creation" in electron_doc
    assert "block top-level navigation away from the local Django origin" in electron_doc
    assert "Tauri uses a bootstrap HttpOnly cookie" in tauri_doc
    assert "fallback `DJANGO_SECRET_KEY` value as Electron and Tauri" in positron_doc
    assert "not a release-parity path in this slice" in positron_doc
    assert "Positron uses a bootstrap HttpOnly cookie" in positron_doc
    assert "single running instance per app-data directory with a lock file" in positron_doc
    assert "always uses the packaged Django settings module" in positron_doc
    assert "without clearing the cache-backed staticfiles tree on every launch" in positron_doc
    assert "app-data lock file" in architecture
    assert "For the experimental Positron shell" in readme
    assert "single running instance per app-data directory with a lock file" in readme
    assert (
        "refreshes collected static files on startup without clearing the cache directory each time"
        in readme
    )
    assert ".stage/" in gitignore
    assert "now wired into Electron startup" in (ROOT / "docs" / "design-guide.md").read_text()


def test_packaging_workflow_mentions_signing_and_checksum_steps() -> None:
    workflow = (ROOT / ".github" / "workflows" / "desktop-packages.yml").read_text()

    assert "Prepare macOS notarization API key" in workflow
    assert "APPLE_API_KEY_ID" in workflow
    assert "WIN_CSC_LINK" in workflow
    assert "publish_release" in workflow
    assert "contents: write" in workflow
    assert "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in workflow
    electron_publish_env = (
        "ELECTRON_RELEASE_PUBLISH: ${{ inputs.publish_release && 'always' || 'never' }}"
    )
    assert electron_publish_env in workflow
    assert 'npx electron-builder --publish "$ELECTRON_RELEASE_PUBLISH"' in workflow
    assert "APPLE_API_KEY_CONTENT: ${{ secrets.APPLE_API_KEY }}" in workflow
    assert "env.APPLE_API_KEY_CONTENT != ''" in workflow
    assert "secrets.APPLE_API_KEY != ''" not in workflow
    assert "shell: bash" in workflow
    assert 'if [ -z "${!name:-}" ]; then' in workflow
    assert 'unset "$name"' in workflow
    assert "shells/electron/package-lock.json" in workflow
    assert "npm --prefix shells/electron ci" in workflow
    assert "npm --prefix shells/electron run stage-backend" in workflow
    assert "python scripts/write-checksums.py" in workflow
    assert "latest-mac.yml" in workflow
    assert "latest.yml" in workflow
    assert "latest-linux.yml" in workflow
    assert "*.blockmap" in workflow
    assert "shells/electron/dist/*.zip" in workflow
    assert "Generate artifact checksums" in workflow
    assert "write-checksums.py" in workflow
    assert "Upload packaged desktop artifact checksums" in workflow
    assert "desktop-django-starter-macos-sha256.txt" in workflow
    assert "shells/tauri" not in workflow
    assert "shells/positron" not in workflow


def test_tauri_packaging_workflow_mentions_tauri_action_and_checksums() -> None:
    workflow = (ROOT / ".github" / "workflows" / "tauri-packages.yml").read_text()
    justfile = (ROOT / "justfile").read_text()

    assert "tauri-apps/tauri-action@v0" in workflow
    assert "projectPath: shells/tauri" in workflow
    assert "npm --prefix shells/tauri run stage-backend" in workflow
    assert "shells/tauri/package-lock.json" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "dtolnay/rust-toolchain@stable" in workflow
    assert "swatinem/rust-cache@v2" in workflow
    assert "--no-install-recommends --no-install-suggests" in workflow
    assert "build-essential" in workflow
    assert "libssl-dev" in workflow
    assert "libgtk-3-dev" in workflow
    assert "libwebkit2gtk-4.1-dev" in workflow
    assert "libayatana-appindicator3-dev" in workflow
    assert "libfuse2" in workflow
    assert "file" in workflow
    assert 'NO_STRIP: "true"' in workflow
    assert "Build packaged Linux Tauri artifact" in workflow
    assert "args: --verbose ${{ matrix.bundle_args }}" in workflow
    assert "python scripts/write-checksums.py" in workflow
    assert "desktop-django-starter-tauri-macos-sha256.txt" in workflow
    assert "desktop-django-starter-tauri-windows-sha256.txt" in workflow
    assert "desktop-django-starter-tauri-linux-sha256.txt" in workflow
    assert "tagName:" not in workflow
    assert "releaseName:" not in workflow
    assert "releaseId:" not in workflow
    assert "ubuntu-22.04 # pinned for libwebkit2gtk-4.1-dev availability" in workflow
    assert "gh workflow run tauri-packages.yml" in justfile
    assert "gh run list --workflow tauri-packages.yml" in justfile
    assert "gh run list --workflow desktop-packages.yml" in justfile
    assert 'ln -s "$run_id" dist/github-actions/latest' in justfile
    assert 'ln -s "$run_id" dist/github-actions/tauri/latest' in justfile
    assert "readlink dist/github-actions/latest" in justfile
    assert "readlink dist/github-actions/tauri/latest" in justfile
    assert "desktop-django-starter-tauri-macos-checksums" in justfile


def test_electron_github_download_helper_fetches_checksum_artifacts() -> None:
    justfile = (ROOT / "justfile").read_text()
    claude = (ROOT / "CLAUDE.md").read_text()

    assert "desktop-django-starter-macos-checksums" in justfile
    assert "desktop-django-starter-windows-checksums" in justfile
    assert "desktop-django-starter-linux-checksums" in justfile
    assert "hosted-artifact bundle helpers" in claude

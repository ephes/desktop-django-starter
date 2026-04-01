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
        ROOT / "docs" / "agent-use.md",
        ROOT / "docs" / "multi-shell-plan.md",
        ROOT / "docs" / "shells" / "electron.md",
        ROOT / "docs" / "shells" / "tauri.md",
        ROOT / "docs" / "shells" / "positron.md",
        ROOT / "scripts" / "stage-backend.cjs",
        ROOT / "shells" / "electron" / "package.json",
        ROOT / "shells" / "electron" / "scripts" / "materialize-symlinks.cjs",
        ROOT / "shells" / "tauri" / "package.json",
        ROOT / "shells" / "tauri" / "src-tauri" / "tauri.conf.json",
        ROOT / "shells" / "positron" / "pyproject.toml",
        ROOT / "skills" / "wrap-existing-django-in-electron" / "SKILL.md",
        ROOT / ".github" / "workflows" / "ci.yml",
    ]
    for path in expected:
        assert path.exists(), f"Missing expected file: {path}"


def test_docs_index_references_main_pages() -> None:
    index = (ROOT / "docs" / "index.md").read_text()
    assert "specification" in index
    assert "architecture" in index
    assert "decisions" in index
    assert "release" in index
    assert "agent-use" in index
    assert "shells/electron" in index
    assert "shells/tauri" in index
    assert "shells/positron" in index
    assert "multi-shell-plan" in index


def test_release_docs_cover_signing_and_manual_updates() -> None:
    readme = (ROOT / "README.md").read_text()
    release = (ROOT / "docs" / "release.md").read_text()
    architecture = (ROOT / "docs" / "architecture.md").read_text()
    plan = (ROOT / "docs" / "multi-shell-plan.md").read_text()
    llms = (ROOT / "llms.txt").read_text()
    gitignore = (ROOT / ".gitignore").read_text()

    assert "docs/release.md" in readme
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
    assert "just positron-start" in readme
    assert "just positron-package-dmg" in readme
    assert "APPLE_API_KEY_ID" in release
    assert "WIN_CSC_LINK" in release
    assert "shells/electron/signing/" in release
    assert "just tauri-build" in release
    assert "no dedicated Tauri GitHub packaging workflow" in release
    assert "real live Windows machine test" in release
    assert "no dedicated Positron GitHub packaging workflow" in release
    assert "just positron-package-dmg" in release
    assert "air-gapped" in release
    assert "app.sqlite3" in release
    assert "auto-update" in release
    assert "desktop-django-starter-macos-sha256.txt" in release
    assert "desktop-django-starter-windows-sha256.txt" in release
    assert "promote both files together" in release
    assert "Linux verification" in release
    assert "assets/brand/" in architecture
    assert ".stage/backend/" in architecture
    assert "shells/electron/" in architecture
    assert "shells/tauri/" in architecture
    assert "shells/positron/" in architecture
    assert "packaged-app copy first" in architecture
    assert "shell-local splash window" in architecture
    assert "prepared local bundle path without a real live Windows test" in plan
    assert "real live Windows install/run test is still outstanding" in plan
    assert "shells/electron/" in llms
    assert "shells/tauri/" in llms
    assert "shells/positron/" in llms
    assert "assets/brand/" in llms
    assert "prepared, unverified local Windows NSIS bundle path" in llms
    assert ".stage/" in gitignore


def test_packaging_workflow_mentions_signing_and_checksum_steps() -> None:
    workflow = (ROOT / ".github" / "workflows" / "desktop-packages.yml").read_text()

    assert "Prepare macOS notarization API key" in workflow
    assert "APPLE_API_KEY_ID" in workflow
    assert "WIN_CSC_LINK" in workflow
    assert "APPLE_API_KEY_CONTENT: ${{ secrets.APPLE_API_KEY }}" in workflow
    assert "env.APPLE_API_KEY_CONTENT != ''" in workflow
    assert "secrets.APPLE_API_KEY != ''" not in workflow
    assert "shell: bash" in workflow
    assert 'if [ -z "${!name:-}" ]; then' in workflow
    assert 'unset "$name"' in workflow
    assert "shells/electron/package-lock.json" in workflow
    assert "npm --prefix shells/electron ci" in workflow
    assert "npm --prefix shells/electron run dist" in workflow
    assert "python shells/electron/scripts/write-checksums.py" in workflow
    assert "Generate artifact checksums" in workflow
    assert "write-checksums.py" in workflow
    assert "Upload packaged desktop artifact checksums" in workflow
    assert "desktop-django-starter-macos-sha256.txt" in workflow
    assert "shells/tauri" not in workflow
    assert "shells/positron" not in workflow

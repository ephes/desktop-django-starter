from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_docs_scaffold_exists() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "llms.txt",
        ROOT / ".readthedocs.yml",
        ROOT / "justfile",
        ROOT / "pyproject.toml",
        ROOT / "docs" / "conf.py",
        ROOT / "docs" / "index.md",
        ROOT / "docs" / "llms.txt",
        ROOT / "docs" / "specification.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "decisions.md",
        ROOT / "docs" / "release.md",
        ROOT / "docs" / "agent-use.md",
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


def test_release_docs_cover_signing_and_manual_updates() -> None:
    readme = (ROOT / "README.md").read_text()
    release = (ROOT / "docs" / "release.md").read_text()

    assert "docs/release.md" in readme
    assert "SHA-256" in readme
    assert "APPLE_API_KEY_ID" in release
    assert "WIN_CSC_LINK" in release
    assert "air-gapped" in release
    assert "app.sqlite3" in release
    assert "auto-update" in release
    assert "desktop-django-starter-macos-sha256.txt" in release
    assert "desktop-django-starter-windows-sha256.txt" in release
    assert "promote both files together" in release
    assert "Linux verification" in release


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
    assert "Generate artifact checksums" in workflow
    assert "write-checksums.py" in workflow
    assert "Upload packaged desktop artifact checksums" in workflow
    assert "desktop-django-starter-macos-sha256.txt" in workflow

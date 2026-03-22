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
    assert "APPLE_API_KEY_ID" in release
    assert "WIN_CSC_LINK" in release
    assert "air-gapped" in release
    assert "app.sqlite3" in release
    assert "auto-update" in release


def test_packaging_workflow_mentions_optional_signing_inputs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "desktop-packages.yml").read_text()

    assert "Prepare macOS notarization API key" in workflow
    assert "APPLE_API_KEY_ID" in workflow
    assert "WIN_CSC_LINK" in workflow

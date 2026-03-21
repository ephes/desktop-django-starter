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
    assert "agent-use" in index

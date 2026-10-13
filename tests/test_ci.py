from pathlib import Path


def test_ci_runs_required_typechecks_on_every_platform():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "      - name: Typecheck\n" in workflow
    step = workflow.split("      - name: Typecheck\n", 1)[1].split("\n      - ", 1)[0]
    assert "        shell: bash\n" in step
    assert "continue-on-error:" not in step
    assert "if:" not in step
    assert "          - ubuntu-latest\n" in workflow
    assert "          - macos-latest\n" in workflow
    assert "          - windows-latest\n" in workflow
    justfile = (root / "justfile").read_text(encoding="utf-8")
    assert "\ntypecheck:\n" in justfile
    recipe = justfile.split("\ntypecheck:\n", 1)[1].split("\n\n", 1)[0]
    commands = "\n".join(line.strip() for line in recipe.splitlines())
    actual = "\n".join(line.strip() for line in step.split("        run: |\n", 1)[1].splitlines())
    assert actual == commands.replace("uv run ", "uv run --locked ")
    assert workflow.index("      - name: Typecheck\n") > workflow.index("uv sync --locked")

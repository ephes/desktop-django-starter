import os
from pathlib import Path

import pytest

from desktop_django_starter import devtools
from desktop_django_starter.devtools import (
    _aggregate_cloc_csv,
    _is_excluded_dir,
    bucket_for_path,
)


def test_bucket_for_path_groups_repo_sections() -> None:
    assert bucket_for_path("manage.py") == "."
    assert bucket_for_path("./manage.py") == "."
    assert bucket_for_path("src/example_app/models.py") == "src/example_app"
    assert (
        bucket_for_path("src/desktop_django_starter/settings/local.py")
        == "src/desktop_django_starter"
    )
    assert bucket_for_path("tests/test_health.py") == "tests"
    assert bucket_for_path("tests/integration/test_packaged.py") == "tests/integration"
    assert bucket_for_path("shells/electron/main.js") == "shells/electron"
    assert bucket_for_path("shells/tauri/src-tauri/src/lib.rs") == "shells/tauri"


def test_cloc_report_uses_one_scan(monkeypatch, capsys) -> None:
    from unittest.mock import Mock

    first_detail = (
        'language,filename,blank,comment,code,"github.com/AlDanial/cloc v 2.12"\n'
        'Python,"./src/app/models,old.py",1,2,10\n'
        "Python,./tests/test_health.py,2,0,5\n"
        "JavaScript,./shells/electron/main.js,0,1,20\n"
        "SUM,,3,3,35\n"
        "HTML,./bad.html,invalid,1,20\n"
        "Python\n"
    )
    first_summary = "files,language,blank,comment,code\n3,SUM,3,3,35\n"
    second_detail = first_detail.replace(",1,2,10", ",1,2,90")

    def scan(command, **kwargs):
        if run.call_count > 1:
            output = second_detail
        else:
            output = first_detail if "--by-file" in command else first_summary
        kwargs["stdout"].write(output)
        return devtools.subprocess.CompletedProcess(command, 0)

    run = Mock(side_effect=scan)
    monkeypatch.setattr(devtools.subprocess, "run", run)
    monkeypatch.setattr(devtools.shutil, "which", lambda _: "cloc")
    monkeypatch.setattr(devtools, "Console", None)

    assert devtools.count_lines_of_code() == 0
    run.assert_called_once()
    assert "--by-file" in run.call_args.args[0]
    assert run.call_args.kwargs["timeout"] == 30
    output = capsys.readouterr().out
    assert "github.com/AlDanial/cloc v 2.12" in output
    assert "Lines of code counted successfully with cloc!" in output
    rows = [line.split() for line in output.splitlines() if line.startswith("|")]
    assert "| JavaScript | 1 | 0 | 1 | 20 |".split() in rows
    assert "| Python | 2 | 3 | 2 | 15 |".split() in rows
    assert "| SUM | 3 | 3 | 3 | 35 |".split() in rows
    assert "| src/app | 1 | 10 |".split() in rows
    assert "| tests | 1 | 5 |".split() in rows
    assert "| shells/electron | 1 | 20 |".split() in rows


def test_aggregate_cloc_csv_sums_by_bucket() -> None:
    csv_output = """language,filename,blank,comment,code
Python,./src/example_app/models.py,1,2,10
Python,./src/example_app/views.py,1,2,20
JavaScript,./shells/electron/main.js,1,2,30
Python,./tests/test_health.py,1,2,5
SUM,,4,8,65
"""

    _, _, stats = _aggregate_cloc_csv(csv_output)

    assert stats == {
        "src/example_app": {"files": 2, "lines": 30},
        "shells/electron": {"files": 1, "lines": 30},
        "tests": {"files": 1, "lines": 5},
    }


def test_excluded_dirs_cover_generated_shell_artifacts() -> None:
    assert _is_excluded_dir("shells/positron/.briefcase")
    assert _is_excluded_dir("shells/positron/build")
    assert _is_excluded_dir("shells/positron/dist")
    assert _is_excluded_dir("shells/positron/logs")
    assert _is_excluded_dir("shells/positron/macOS")
    assert _is_excluded_dir("shells/tauri/node_modules")
    assert _is_excluded_dir("shells/tauri/src-tauri/target")
    assert _is_excluded_dir("tauri")
    assert _is_excluded_dir("positron")


def test_python_fallback_prunes_excluded_trees(monkeypatch, tmp_path, capsys) -> None:
    excluded = {tmp_path / "node_modules", tmp_path / "shells/tauri/src-tauri/target"}
    sources = {
        tmp_path / "src/app/models.py": "first\nsecond\n",
        tmp_path / "src/app/build/helper.py": "third\n",
        **{directory / "nested/ignored.py": "ignored\n" for directory in excluded},
    }
    for path, content in sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    scanned = set()
    real_scandir = os.scandir

    def record_scan(directory):
        scanned.add(Path(directory))
        return real_scandir(directory)

    monkeypatch.setattr(os, "scandir", record_scan)
    monkeypatch.setattr(devtools.shutil, "which", lambda _: None)
    monkeypatch.setattr(devtools, "Console", None)
    monkeypatch.chdir(tmp_path)

    assert devtools.count_lines_of_code() == 0
    output = capsys.readouterr().out
    assert "| Python   |     2 |     3 |" in output
    assert "| src/app   |     2 |     3 |" in output
    assert all(directory in scanned for directory in (tmp_path, tmp_path / "src/app/build"))
    assert not any(directory.is_relative_to(tree) for directory in scanned for tree in excluded)


@pytest.mark.parametrize("backend", ["cloc", "python"])
def test_empty_plain_line_count_succeeds(backend, monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(devtools, "Console", None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(devtools.shutil, "which", lambda _: "cloc" if backend == "cloc" else None)
    monkeypatch.setattr(devtools, "_run_cloc", lambda _: "")

    assert devtools.count_lines_of_code() == 0

    output = capsys.readouterr().out
    assert "Overall Summary:" in output
    assert "| Language | Files |" in output
    assert "Lines of Code by Directory\n" + devtools._render_table("Directory", []) in output
    assert (
        f"Lines of code counted successfully with {backend if backend == 'cloc' else 'Python'}!"
        in output
    )
    if backend == "python":
        assert "| SUM      |     0 |     0 |" in output


@pytest.mark.parametrize(
    ("rows", "expected_rows"),
    [
        ([("src", "1", "20")], ["| src       |     1 |    20 |"]),
        (
            [("src/example_app", "12", "1000"), ("tests", "2", "30")],
            ["| src/example_app |    12 |  1000 |", "| tests           |     2 |    30 |"],
        ),
    ],
)
def test_plain_table_preserves_alignment(rows, expected_rows) -> None:
    lines = devtools._render_table("Directory", rows).splitlines()
    assert lines[3:-1] == expected_rows
    assert len({len(line) for line in lines}) == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (devtools.subprocess.TimeoutExpired("cloc", 30), "cloc timed out after 30 seconds."),
        (FileNotFoundError("missing"), "Could not start cloc."),
        (PermissionError("denied"), "Could not start cloc."),
    ],
)
def test_cloc_execution_failures_exit_without_summary(error, message, monkeypatch, capsys):
    from unittest.mock import Mock

    monkeypatch.setattr(devtools.shutil, "which", lambda _: "cloc")
    run = Mock(side_effect=error)
    monkeypatch.setattr(devtools.subprocess, "run", run)
    fallback = Mock()
    monkeypatch.setattr(devtools, "_count_with_python", fallback)

    with pytest.raises(SystemExit) as exc:
        devtools.count_lines_of_code()

    assert exc.value.code == 1
    run.assert_called_once()
    for call in run.call_args_list:
        assert call.kwargs == {
            "check": True,
            "stdout": call.kwargs["stdout"],
            "stderr": call.kwargs["stderr"],
            "text": True,
            "timeout": 30,
        }
        assert call.kwargs["stdout"].closed
        assert call.kwargs["stderr"].closed
    fallback.assert_not_called()
    captured = capsys.readouterr()
    assert captured.err == message + "\n"
    assert captured.out == ""


def test_cloc_real_child_is_killed_and_reaped_on_timeout(monkeypatch, capsys):
    processes = []
    real_popen = devtools.subprocess.Popen

    def record_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(devtools.subprocess, "Popen", record_process)
    monkeypatch.setattr(devtools, "CLOC_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(SystemExit) as exc:
        devtools._run_cloc([devtools.sys.executable, "-c", "import time; time.sleep(60)"])
    assert exc.value.code == 1
    assert len(processes) == 1
    assert processes[0].returncode is not None
    assert processes[0].returncode != 0
    assert capsys.readouterr().err == "cloc timed out after 0.1 seconds.\n"


def test_cloc_nonzero_child_preserves_stderr_and_exit_code(capsys):
    with pytest.raises(SystemExit) as exc:
        devtools._run_cloc(
            [
                devtools.sys.executable,
                "-c",
                "import sys; print('cloc failed', file=sys.stderr); sys.exit(3)",
            ]
        )
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert captured.err == "cloc failed\n"
    assert captured.out == ""

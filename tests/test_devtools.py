import pytest

from desktop_django_starter import devtools
from desktop_django_starter.devtools import (
    _aggregate_cloc_csv,
    _is_excluded_dir,
    _parse_cloc_summary_csv,
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


def test_aggregate_cloc_csv_sums_by_bucket() -> None:
    csv_output = """language,filename,blank,comment,code
Python,./src/example_app/models.py,1,2,10
Python,./src/example_app/views.py,1,2,20
JavaScript,./shells/electron/main.js,1,2,30
Python,./tests/test_health.py,1,2,5
SUM,,4,8,65
"""

    stats = _aggregate_cloc_csv(csv_output)

    assert stats == {
        "src/example_app": {"files": 2, "lines": 30},
        "shells/electron": {"files": 1, "lines": 30},
        "tests": {"files": 1, "lines": 5},
    }


def test_parse_cloc_summary_csv_keeps_metadata_and_sum_row() -> None:
    csv_output = """files,language,blank,comment,code,"github.com/AlDanial/cloc v 2.08"
11,JavaScript,214,14,1119
26,Python,163,30,500
53,SUM,495,52,2238
bad,HTML,8,0,107
"""

    parsed = _parse_cloc_summary_csv(csv_output)

    assert parsed == {
        "metadata": "github.com/AlDanial/cloc v 2.08",
        "rows": [
            {
                "language": "JavaScript",
                "files": 11,
                "blank": 214,
                "comment": 14,
                "code": 1119,
            },
            {
                "language": "Python",
                "files": 26,
                "blank": 163,
                "comment": 30,
                "code": 500,
            },
            {
                "language": "SUM",
                "files": 53,
                "blank": 495,
                "comment": 52,
                "code": 2238,
            },
        ],
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


@pytest.mark.parametrize("failed_invocation", [1, 2])
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (devtools.subprocess.TimeoutExpired("cloc", 30), "cloc timed out after 30 seconds."),
        (FileNotFoundError("missing"), "Could not start cloc."),
        (PermissionError("denied"), "Could not start cloc."),
    ],
)
def test_cloc_execution_failures_exit_without_summary(
    failed_invocation, error, message, monkeypatch, capsys
):
    from unittest.mock import Mock

    monkeypatch.setattr(devtools.shutil, "which", lambda _: "cloc")
    run = Mock(
        side_effect=[devtools.subprocess.CompletedProcess([], 0, stdout="")]
        * (failed_invocation - 1)
        + [error]
    )
    monkeypatch.setattr(devtools.subprocess, "run", run)
    fallback = Mock()
    monkeypatch.setattr(devtools, "_count_with_python", fallback)

    with pytest.raises(SystemExit) as exc:
        devtools.count_lines_of_code()

    assert exc.value.code == 1
    assert run.call_count == failed_invocation
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


def test_cloc_success_runs_summary_and_detail_with_timeout(monkeypatch, capsys):
    from unittest.mock import Mock

    monkeypatch.setattr(devtools, "Console", None)
    monkeypatch.setattr(devtools.shutil, "which", lambda _: "cloc")

    def successful_run(command, **kwargs):
        csv = (
            "language,filename,blank,comment,code\nPython,src/app/a.py,0,0,5\n"
            if "--by-file" in command
            else "files,language,blank,comment,code\n1,Python,0,0,5\n"
        )
        kwargs["stdout"].write(csv)
        return devtools.subprocess.CompletedProcess(command, 0)

    run = Mock(side_effect=successful_run)
    monkeypatch.setattr(devtools.subprocess, "run", run)

    assert devtools.count_lines_of_code() == 0
    assert run.call_count == 2
    assert "--by-file" not in run.call_args_list[0].args[0]
    assert "--by-file" in run.call_args_list[1].args[0]
    assert all(call.kwargs["timeout"] == 30 for call in run.call_args_list)
    output = capsys.readouterr().out
    assert "Python" in output
    assert "src/app" in output
    assert "Lines of code counted successfully with cloc!" in output


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

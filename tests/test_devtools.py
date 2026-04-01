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
    assert bucket_for_path("shells/electron/main.js") == "shells"


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
        "shells": {"files": 1, "lines": 30},
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

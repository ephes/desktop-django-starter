# Justfile for desktop-django-starter

default:
    @just --list

install:
    uv sync

test:
    uv run pytest

test-one TARGET:
    uv run pytest {{TARGET}} -v

lint:
    uv run ruff check .

format:
    uv run ruff format .

check:
    just lint
    just test
    just docs-build

migrate:
    uv run python manage.py migrate --noinput

backend-dev:
    just migrate
    uv run python manage.py runserver 127.0.0.1:8000

task-worker:
    just migrate
    uv run python manage.py db_worker --queue-name default --worker-id desktop-django-starter

electron-install:
    npm --prefix electron install

electron-start:
    npm --prefix electron start

packaged-stage:
    npm --prefix electron run stage-backend

packaged-start:
    npm --prefix electron run start:packaged

packaged-smoke:
    npm --prefix electron run smoke:packaged

package-dist TARGET="--mac dmg":
    npm --prefix electron run dist -- {{TARGET}}

package-dist-dir TARGET="--mac":
    npm --prefix electron run dist:dir -- {{TARGET}}

github-package BRANCH="":
    @branch="{{BRANCH}}"; \
    if [ -z "$branch" ]; then branch="$(git symbolic-ref --short -q HEAD)"; fi; \
    [ -n "$branch" ] || { echo "Unable to determine a branch. Pass the branch name as the first argument."; exit 1; }; \
    gh workflow run desktop-packages.yml --ref "$branch"

github-package-download RUN_ID:
    @set -eu; \
    run_dir="dist/github-actions/{{RUN_ID}}"; \
    rm -rf "$run_dir"; \
    mkdir -p "$run_dir"; \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-macos --dir "$run_dir/macos" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-windows --dir "$run_dir/windows" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-linux --dir "$run_dir/linux" && \
    echo "Downloaded workflow artifacts to $run_dir"; \
    echo "macOS:   $run_dir/macos"; \
    echo "Windows: $run_dir/windows"; \
    echo "Linux:   $run_dir/linux"

github-package-latest-run BRANCH="":
    @set -eu; \
    branch="{{BRANCH}}"; \
    if [ -z "$branch" ]; then branch="$(git symbolic-ref --short -q HEAD)"; fi; \
    [ -n "$branch" ] || { echo "Unable to determine a branch. Pass the branch name as the first argument."; exit 1; }; \
    run_id="$(gh run list --workflow desktop-packages.yml --branch "$branch" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"; \
    [ -n "$run_id" ] && [ "$run_id" != "null" ] || { echo "No successful desktop-packages.yml run found for branch $branch."; exit 1; }; \
    echo "$run_id"

github-package-latest-path:
    @set -eu; \
    if [ -f dist/github-actions/latest-run.txt ]; then \
        run_id="$(cat dist/github-actions/latest-run.txt)"; \
        run_dir="dist/github-actions/$run_id"; \
        [ -d "$run_dir" ] || { echo "Recorded latest run $run_id is not downloaded locally."; exit 1; }; \
        echo "$run_dir"; \
        exit 0; \
    fi; \
    run_dir="$(find dist/github-actions -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' -print 2>/dev/null | sort | tail -n 1)"; \
    [ -n "$run_dir" ] || { echo "No downloaded GitHub package runs found under dist/github-actions."; exit 1; }; \
    echo "$run_dir"

github-package-download-latest BRANCH="":
    @set -eu; \
    branch="{{BRANCH}}"; \
    if [ -z "$branch" ]; then branch="$(git symbolic-ref --short -q HEAD)"; fi; \
    [ -n "$branch" ] || { echo "Unable to determine a branch. Pass the branch name as the first argument."; exit 1; }; \
    run_id="$(gh run list --workflow desktop-packages.yml --branch "$branch" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"; \
    [ -n "$run_id" ] && [ "$run_id" != "null" ] || { echo "No successful desktop-packages.yml run found for branch $branch."; exit 1; }; \
    echo "Latest successful run for $branch: $run_id"; \
    just github-package-download "$run_id"; \
    mkdir -p dist/github-actions; \
    printf "%s\n" "$run_id" > dist/github-actions/latest-run.txt; \
    echo "Latest downloaded path: dist/github-actions/$run_id"

dev:
    just electron-start

docs-build:
    uv run sphinx-build -M html docs docs/_build

docs:
    just docs-build
    uv run python -c "from pathlib import Path; import webbrowser; webbrowser.open(Path('docs/_build/html/index.html').resolve().as_uri())"

docs-serve:
    uv run sphinx-autobuild --open-browser docs docs/_build/html

build:
    uv build

# Count lines of code in the repository with an overall summary and folder breakdown
loc:
    uv run count-lines-of-code

clean:
    rm -rf build dist docs/_build .pytest_cache .ruff_cache *.egg-info db.sqlite3 electron/dist electron/node_modules electron/.stage

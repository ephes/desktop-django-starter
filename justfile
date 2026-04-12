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

typecheck:
    uv run mypy src/
    for f in shells/electron/main.js shells/electron/preload.cjs shells/electron/electron-builder.config.cjs shells/electron/scripts/*.cjs scripts/*.cjs shells/tauri/scripts/*.mjs; do node --check "$f" || exit 1; done

check:
    just lint
    just typecheck
    just test
    npm --prefix shells/electron test
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
    npm --prefix shells/electron install

electron-start:
    npm --prefix shells/electron start

tauri-install:
    npm --prefix shells/tauri install

tauri-test:
    npm --prefix shells/tauri test

tauri-start:
    npm --prefix shells/tauri start

tauri-smoke:
    npm --prefix shells/tauri run smoke

tauri-packaged-start:
    npm --prefix shells/tauri run start:packaged

tauri-packaged-smoke:
    npm --prefix shells/tauri run smoke:packaged

tauri-build TARGET="":
    npm --prefix shells/tauri run build -- {{TARGET}}

positron-install:
    env -u VIRTUAL_ENV uv sync --project shells/positron

positron-icons:
    env -u VIRTUAL_ENV uv run --project shells/positron python ./shells/positron/scripts/generate-icons.py

positron-check:
    env -u VIRTUAL_ENV uv run --project shells/positron python -m desktop_django_starter_positron.management check

positron-start:
    env -u VIRTUAL_ENV uv run --project shells/positron python -m desktop_django_starter_positron

positron-smoke:
    env -u VIRTUAL_ENV DESKTOP_DJANGO_SMOKE_TEST=1 uv run --project shells/positron python -m desktop_django_starter_positron

positron-create:
    just positron-icons
    cd shells/positron && env -u VIRTUAL_ENV uvx briefcase create macOS app --no-input -a desktop_django_starter_positron

positron-build:
    just positron-icons
    @if [ ! -d shells/positron/build/desktop_django_starter_positron/macos/app ]; then just positron-create; fi
    cd shells/positron && env -u VIRTUAL_ENV uvx briefcase build macOS app --update-resources --no-input -a desktop_django_starter_positron

positron-package-dmg:
    just positron-build
    cd shells/positron && env -u VIRTUAL_ENV uvx briefcase package macOS app --packaging-format dmg --adhoc-sign --no-notarize --no-input -a desktop_django_starter_positron

packaged-stage:
    npm --prefix shells/electron run stage-backend

packaged-start:
    npm --prefix shells/electron run start:packaged

packaged-smoke:
    npm --prefix shells/electron run smoke:packaged

electron-package-dmg: (package-dist "--mac dmg")

# Skip staging + signing for fast iteration. Run `just packaged-stage` first.
electron-package-dmg-fast:
    @test -d .stage/backend || { echo "Error: .stage/backend not found. Run 'just packaged-stage' first." >&2; exit 1; }
    cd shells/electron && npx electron-builder --publish never --mac dmg --config ./electron-builder.config.cjs --config.mac.identity=null

package-dist TARGET="--mac dmg":
    npm --prefix shells/electron run dist -- {{TARGET}}

package-dist-dir TARGET="--mac":
    npm --prefix shells/electron run dist:dir -- {{TARGET}}

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
    gh run download "{{RUN_ID}}" --name desktop-django-starter-macos-checksums --dir "$run_dir/macos" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-windows --dir "$run_dir/windows" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-windows-checksums --dir "$run_dir/windows" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-linux --dir "$run_dir/linux" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-linux-checksums --dir "$run_dir/linux" && \
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
    if [ -L dist/github-actions/latest ]; then \
        latest_path="$(readlink dist/github-actions/latest)"; \
        echo "dist/github-actions/$latest_path"; \
        exit 0; \
    fi; \
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
    rm -f dist/github-actions/latest; \
    if ln -s "$run_id" dist/github-actions/latest 2>/dev/null; then \
        echo "Latest symlink: dist/github-actions/latest"; \
    else \
        echo "Latest symlink not created; using dist/github-actions/latest-run.txt instead."; \
    fi; \
    echo "Latest downloaded path: dist/github-actions/$run_id"

github-package-tauri BRANCH="":
    @branch="{{BRANCH}}"; \
    if [ -z "$branch" ]; then branch="$(git symbolic-ref --short -q HEAD)"; fi; \
    [ -n "$branch" ] || { echo "Unable to determine a branch. Pass the branch name as the first argument."; exit 1; }; \
    gh workflow run tauri-packages.yml --ref "$branch"

github-package-tauri-download RUN_ID:
    @set -eu; \
    run_dir="dist/github-actions/tauri/{{RUN_ID}}"; \
    rm -rf "$run_dir"; \
    mkdir -p "$run_dir"; \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-tauri-macos --dir "$run_dir/macos" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-tauri-macos-checksums --dir "$run_dir/macos" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-tauri-windows --dir "$run_dir/windows" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-tauri-windows-checksums --dir "$run_dir/windows" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-tauri-linux --dir "$run_dir/linux" && \
    gh run download "{{RUN_ID}}" --name desktop-django-starter-tauri-linux-checksums --dir "$run_dir/linux" && \
    echo "Downloaded Tauri workflow artifacts to $run_dir"; \
    echo "macOS:   $run_dir/macos"; \
    echo "Windows: $run_dir/windows"; \
    echo "Linux:   $run_dir/linux"

github-package-tauri-latest-run BRANCH="":
    @set -eu; \
    branch="{{BRANCH}}"; \
    if [ -z "$branch" ]; then branch="$(git symbolic-ref --short -q HEAD)"; fi; \
    [ -n "$branch" ] || { echo "Unable to determine a branch. Pass the branch name as the first argument."; exit 1; }; \
    run_id="$(gh run list --workflow tauri-packages.yml --branch "$branch" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"; \
    [ -n "$run_id" ] && [ "$run_id" != "null" ] || { echo "No successful tauri-packages.yml run found for branch $branch."; exit 1; }; \
    echo "$run_id"

github-package-tauri-latest-path:
    @set -eu; \
    if [ -L dist/github-actions/tauri/latest ]; then \
        latest_path="$(readlink dist/github-actions/tauri/latest)"; \
        echo "dist/github-actions/tauri/$latest_path"; \
        exit 0; \
    fi; \
    if [ -f dist/github-actions/tauri/latest-run.txt ]; then \
        run_id="$(cat dist/github-actions/tauri/latest-run.txt)"; \
        run_dir="dist/github-actions/tauri/$run_id"; \
        [ -d "$run_dir" ] || { echo "Recorded latest Tauri run $run_id is not downloaded locally."; exit 1; }; \
        echo "$run_dir"; \
        exit 0; \
    fi; \
    run_dir="$(find dist/github-actions/tauri -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' -print 2>/dev/null | sort | tail -n 1)"; \
    [ -n "$run_dir" ] || { echo "No downloaded Tauri package runs found under dist/github-actions/tauri."; exit 1; }; \
    echo "$run_dir"

github-package-tauri-download-latest BRANCH="":
    @set -eu; \
    branch="{{BRANCH}}"; \
    if [ -z "$branch" ]; then branch="$(git symbolic-ref --short -q HEAD)"; fi; \
    [ -n "$branch" ] || { echo "Unable to determine a branch. Pass the branch name as the first argument."; exit 1; }; \
    run_id="$(gh run list --workflow tauri-packages.yml --branch "$branch" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"; \
    [ -n "$run_id" ] && [ "$run_id" != "null" ] || { echo "No successful tauri-packages.yml run found for branch $branch."; exit 1; }; \
    echo "Latest successful Tauri run for $branch: $run_id"; \
    just github-package-tauri-download "$run_id"; \
    mkdir -p dist/github-actions/tauri; \
    printf "%s\n" "$run_id" > dist/github-actions/tauri/latest-run.txt; \
    rm -f dist/github-actions/tauri/latest; \
    if ln -s "$run_id" dist/github-actions/tauri/latest 2>/dev/null; then \
        echo "Latest Tauri symlink: dist/github-actions/tauri/latest"; \
    else \
        echo "Latest Tauri symlink not created; using dist/github-actions/tauri/latest-run.txt instead."; \
    fi; \
    echo "Latest downloaded path: dist/github-actions/tauri/$run_id"

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

# CLI package (cli/)
cli-sync-assets:
    python cli/sync_assets.py

cli-build: cli-sync-assets
    rm -rf cli/dist
    cd cli && env -u VIRTUAL_ENV uv build

cli-test: cli-sync-assets
    cd cli && env -u VIRTUAL_ENV uv run --with pytest python -m pytest tests/

cli-publish: cli-test cli-build
    cd cli && env -u VIRTUAL_ENV uv publish dist/desktop_django_starter-*.tar.gz dist/desktop_django_starter-*-py3-none-any.whl

clean:
    rm -rf build dist docs/_build .pytest_cache .ruff_cache *.egg-info db.sqlite3 .stage shells/electron/dist shells/electron/node_modules shells/tauri/node_modules shells/tauri/src-tauri/target shells/positron/.briefcase shells/positron/.venv shells/positron/build shells/positron/dist shells/positron/linux shells/positron/logs shells/positron/macOS shells/positron/windows shells/positron/resources/app-icon.icns shells/positron/resources/app-icon.png

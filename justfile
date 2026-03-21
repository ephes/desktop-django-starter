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

electron-install:
    npm --prefix electron install

electron-start:
    npm --prefix electron start

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

# Count lines of code in the repository (by language + by top-level folder)
loc:
    cloc --vcs=git .
    @echo ""
    @echo "--- Python SLOC by folder ---"
    @sloccount --details . 2>/dev/null | awk '/^[0-9]/ && $2=="python" {sums[$3]+=$1} END{for(d in sums) printf "%8d  %s\n", sums[d], d}' | sort -rn

clean:
    rm -rf build dist docs/_build .pytest_cache .ruff_cache *.egg-info db.sqlite3 electron/node_modules

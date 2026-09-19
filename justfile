set dotenv-load := true
set shell := ["bash", "-euo", "pipefail", "-c"]

_default:
    @just --list

# Install the locked runtime and development dependencies.
setup:
    uv sync --locked --all-groups

# Format all Python code.
format:
    uv run ruff format .

# Check formatting without changing files.
format-check:
    uv run ruff format --check .

# Run the linter.
lint:
    uv run ruff check .

# Run the static type checker.
typecheck:
    uv run pyright

# Run all offline tests; pass extra pytest arguments after `--`.
test *args:
    uv run pytest -m "not live" {{args}}

# Run live API tests after loading TYPESAFE_API_KEY from .env.
test-live *args:
    @test -n "${TYPESAFE_API_KEY:-}" || { echo "TYPESAFE_API_KEY is missing; add it to .env." >&2; exit 1; }
    uv run pytest -m live {{args}}

# Run formatting, linting, types, and all offline tests.
check: format-check lint typecheck test

# Run one demo from its repo-relative folder with an offline fixture.
demo demo="critical/fraud-screening" scenario="confident":
    uv run python "{{demo}}/demo.py" --scenario "{{scenario}}"

# Run one demo against the live TypeSafe API.
demo-live demo="critical/fraud-screening":
    @test -n "${TYPESAFE_API_KEY:-}" || { echo "TYPESAFE_API_KEY is missing; add it to .env." >&2; exit 1; }
    uv run python "{{demo}}/demo.py" --live

# Launch the local visual gallery; pass `--no-browser --port 8080` for options.
gallery *args:
    uv run garage {{args}}

# Reproduce the offline GitHub Actions gate from a locked environment.
ci: setup check

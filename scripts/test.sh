#!/usr/bin/env bash
# What CI runs: install deps, lint, then every test except live ones.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  pip install --quiet uv
fi

uv sync --quiet
uv run ruff check .
uv run pytest -m "not live" -q

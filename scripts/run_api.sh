#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv python at $VENV_PYTHON" >&2
  exit 1
fi

cd "$REPO_ROOT"

if [[ -f "$REPO_ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env.local"
  set +a
fi

export PYTHONPATH="$REPO_ROOT/src"
export OPENHAMSTER_STARTUP_MODE="${OPENHAMSTER_STARTUP_MODE:-script}"

exec "$VENV_PYTHON" -m openhamster.api.main

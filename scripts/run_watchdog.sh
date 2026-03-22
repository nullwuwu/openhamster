#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
STATE_ROOT="${OPENHAMSTER_LOCAL_STATE_ROOT:-$HOME/.openhamster/local-runtime/state}"

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
export OPENHAMSTER_LOG_DIR="${OPENHAMSTER_LOG_DIR:-$STATE_ROOT/logs}"
export RUNTIME_STATE_DB_PATH="${RUNTIME_STATE_DB_PATH:-$STATE_ROOT/var/db/runtime_state.db}"
export RUNTIME_DB_PATH="${RUNTIME_DB_PATH:-$STATE_ROOT/var/db/trading.db}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$STATE_ROOT/var/db/openhamster.db}"
export PAPER_DB_PATH="${PAPER_DB_PATH:-$STATE_ROOT/var/db/paper_trading.db}"
export MARKET_CACHE_PATH="${MARKET_CACHE_PATH:-$STATE_ROOT/var/cache/market_data_cache.db}"
export APP_LOG_PATH="${APP_LOG_PATH:-$STATE_ROOT/var/logs/openhamster.log}"
export OPENHAMSTER_STDOUT_LOG_PATH="${OPENHAMSTER_STDOUT_LOG_PATH:-$STATE_ROOT/logs/openhamster-api.out.log}"
export OPENHAMSTER_STDERR_LOG_PATH="${OPENHAMSTER_STDERR_LOG_PATH:-$STATE_ROOT/logs/openhamster-api.err.log}"

exec "$VENV_PYTHON" -m openhamster.watchdog.local_watchdog

#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${OPENHAMSTER_LOCAL_RUNTIME_ROOT:-$HOME/.openhamster/local-runtime/current}"
STATE_ROOT="${OPENHAMSTER_LOCAL_STATE_ROOT:-$HOME/.openhamster/local-runtime/state}"
BOOTSTRAP_PYTHON="${OPENHAMSTER_RUNTIME_BOOTSTRAP_PYTHON:-$SOURCE_ROOT/.venv/bin/python}"

if [[ ! -x "$BOOTSTRAP_PYTHON" ]]; then
  BOOTSTRAP_PYTHON="$(command -v python3 || command -v python)"
fi

mkdir -p \
  "$RUNTIME_ROOT" \
  "$STATE_ROOT/logs" \
  "$STATE_ROOT/var/db" \
  "$STATE_ROOT/var/cache" \
  "$STATE_ROOT/var/logs" \
  "$STATE_ROOT/var/launchd"

rsync -a --delete \
  --exclude '.git' \
  --exclude '.github' \
  --exclude '.pytest_cache' \
  --exclude '.venv' \
  --exclude 'apps/web/node_modules' \
  --exclude 'logs' \
  --exclude 'var' \
  --exclude '.env.local' \
  "$SOURCE_ROOT/" "$RUNTIME_ROOT/"

if [[ -f "$SOURCE_ROOT/.env.local" ]]; then
  cp "$SOURCE_ROOT/.env.local" "$RUNTIME_ROOT/.env.local"
fi

if [[ ! -x "$RUNTIME_ROOT/.venv/bin/python" ]]; then
  "$BOOTSTRAP_PYTHON" -m venv "$RUNTIME_ROOT/.venv"
fi

cd "$RUNTIME_ROOT"
"$RUNTIME_ROOT/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$RUNTIME_ROOT/.venv/bin/pip" install '.[dev]'

echo "Prepared runtime bundle at $RUNTIME_ROOT"
echo "Persistent state at $STATE_ROOT"

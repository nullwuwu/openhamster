#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHD_LABEL="com.openhamster.api"
LAUNCHD_TARGET="$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"
RUNTIME_ROOT="${OPENHAMSTER_LOCAL_RUNTIME_ROOT:-$HOME/.openhamster/local-runtime/current}"
STATE_ROOT="${OPENHAMSTER_LOCAL_STATE_ROOT:-$HOME/.openhamster/local-runtime/state}"
RENDERED_PLIST="$STATE_ROOT/var/launchd/${LAUNCHD_LABEL}.plist"
HEALTH_URL="http://127.0.0.1:8000/healthz"

cd "$REPO_ROOT"

mkdir -p "$HOME/Library/LaunchAgents" "$STATE_ROOT/logs" "$STATE_ROOT/var/logs" "$STATE_ROOT/var/launchd"

echo "[1/6] Building frontend"
bash "$REPO_ROOT/scripts/build_frontend.sh"

echo "[2/6] Preparing runtime bundle"
OPENHAMSTER_LOCAL_RUNTIME_ROOT="$RUNTIME_ROOT" \
OPENHAMSTER_LOCAL_STATE_ROOT="$STATE_ROOT" \
bash "$REPO_ROOT/scripts/prepare_local_runtime.sh"

echo "[3/6] Rendering launchd plist"
OPENHAMSTER_LAUNCHD_RUNTIME_ROOT="$RUNTIME_ROOT" \
OPENHAMSTER_LAUNCHD_STATE_ROOT="$STATE_ROOT" \
OPENHAMSTER_LAUNCHD_LOG_DIR="$STATE_ROOT/logs" \
OPENHAMSTER_LAUNCHD_OUTPUT_DIR="$STATE_ROOT/var/launchd" \
bash "$REPO_ROOT/scripts/render_launchd_plist.sh"

echo "[4/6] Freeing port 8000"
while read -r pid; do
  [[ -n "$pid" ]] || continue
  kill "$pid" >/dev/null 2>&1 || true
done < <(lsof -tiTCP:8000 -sTCP:LISTEN -n -P || true)

echo "[5/6] Installing launchd plist"
cp "$RENDERED_PLIST" "$LAUNCHD_TARGET"

echo "[6/6] Reloading launchd service"
if launchctl bootout "gui/$(id -u)/${LAUNCHD_LABEL}" >/dev/null 2>&1; then
  :
fi

if ! launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_TARGET"; then
  echo "launchctl bootstrap failed, falling back to unload/load" >&2
  launchctl unload "$LAUNCHD_TARGET" >/dev/null 2>&1 || true
  launchctl load "$LAUNCHD_TARGET"
fi

launchctl kickstart -k "gui/$(id -u)/${LAUNCHD_LABEL}" >/dev/null 2>&1 || true

echo "Waiting for health check"
for _ in {1..30}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "OpenHamster is running at http://127.0.0.1:8000/"
    echo "Logs:"
    echo "  $STATE_ROOT/logs/openhamster-api.out.log"
    echo "  $STATE_ROOT/logs/openhamster-api.err.log"
    echo "Runtime root:"
    echo "  $RUNTIME_ROOT"
    exit 0
  fi
  sleep 1
done

echo "Service did not become healthy in time. Check logs:" >&2
echo "  $STATE_ROOT/logs/openhamster-api.out.log" >&2
echo "  $STATE_ROOT/logs/openhamster-api.err.log" >&2
exit 1

#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHD_LABEL="com.gobyshrimp.api"
LAUNCHD_TARGET="$HOME/Library/LaunchAgents/${LAUNCHD_LABEL}.plist"
RENDERED_PLIST="$REPO_ROOT/var/launchd/${LAUNCHD_LABEL}.plist"
HEALTH_URL="http://127.0.0.1:8000/healthz"

cd "$REPO_ROOT"

mkdir -p "$HOME/Library/LaunchAgents" "$REPO_ROOT/logs" "$REPO_ROOT/var/launchd"

echo "[1/5] Building frontend"
bash "$REPO_ROOT/scripts/build_frontend.sh"

echo "[2/5] Rendering launchd plist"
bash "$REPO_ROOT/scripts/render_launchd_plist.sh"

echo "[3/5] Installing launchd plist"
cp "$RENDERED_PLIST" "$LAUNCHD_TARGET"

echo "[4/5] Reloading launchd service"
if launchctl bootout "gui/$(id -u)/${LAUNCHD_LABEL}" >/dev/null 2>&1; then
  :
fi

if ! launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_TARGET"; then
  echo "launchctl bootstrap failed, falling back to unload/load" >&2
  launchctl unload "$LAUNCHD_TARGET" >/dev/null 2>&1 || true
  launchctl load "$LAUNCHD_TARGET"
fi

launchctl kickstart -k "gui/$(id -u)/${LAUNCHD_LABEL}" >/dev/null 2>&1 || true

echo "[5/5] Waiting for health check"
for _ in {1..30}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "GobyShrimp is running at http://127.0.0.1:8000/"
    echo "Logs:"
    echo "  $REPO_ROOT/logs/gobyshrimp-api.out.log"
    echo "  $REPO_ROOT/logs/gobyshrimp-api.err.log"
    exit 0
  fi
  sleep 1
done

echo "Service did not become healthy in time. Check logs:" >&2
echo "  $REPO_ROOT/logs/gobyshrimp-api.out.log" >&2
echo "  $REPO_ROOT/logs/gobyshrimp-api.err.log" >&2
exit 1

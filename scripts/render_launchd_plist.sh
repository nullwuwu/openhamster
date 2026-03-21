#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${OPENHAMSTER_LAUNCHD_RUNTIME_ROOT:-$REPO_ROOT}"
STATE_ROOT="${OPENHAMSTER_LAUNCHD_STATE_ROOT:-$REPO_ROOT}"
TEMPLATE="$REPO_ROOT/deploy/launchd/com.openhamster.api.plist"
OUTPUT_DIR="${OPENHAMSTER_LAUNCHD_OUTPUT_DIR:-$REPO_ROOT/var/launchd}"
OUTPUT_FILE="$OUTPUT_DIR/com.openhamster.api.plist"
LOG_DIR="${OPENHAMSTER_LAUNCHD_LOG_DIR:-$STATE_ROOT/logs}"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

sed \
  -e "s|__REPO_ROOT__|$RUNTIME_ROOT|g" \
  -e "s|__STATE_ROOT__|$STATE_ROOT|g" \
  -e "s|__LOG_DIR__|$LOG_DIR|g" \
  "$TEMPLATE" > "$OUTPUT_FILE"

echo "Rendered $OUTPUT_FILE"

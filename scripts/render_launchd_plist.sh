#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_ROOT/deploy/launchd/com.openhamster.api.plist"
OUTPUT_DIR="$REPO_ROOT/var/launchd"
OUTPUT_FILE="$OUTPUT_DIR/com.openhamster.api.plist"
LOG_DIR="$REPO_ROOT/logs"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

sed \
  -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
  -e "s|__LOG_DIR__|$LOG_DIR|g" \
  "$TEMPLATE" > "$OUTPUT_FILE"

echo "Rendered $OUTPUT_FILE"

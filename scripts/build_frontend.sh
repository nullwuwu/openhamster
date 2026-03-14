#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT"
npm ci --prefix apps/web --legacy-peer-deps
npm run build --prefix apps/web

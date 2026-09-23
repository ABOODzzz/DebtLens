#!/bin/bash
# Production equivalent of dev.sh: FastAPI backend on an internal port,
# Vite's static preview server (serving the built React app) on the
# artifact's public $PORT, proxying /api/* to FastAPI.
set -e
cd "$(dirname "$0")"

FASTAPI_PORT=8001

(cd server_py && PORT="$FASTAPI_PORT" python3 run.py) &
FASTAPI_PID=$!

cleanup() {
  kill "$FASTAPI_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec pnpm exec vite preview --config vite.config.ts --host 0.0.0.0

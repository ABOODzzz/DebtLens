#!/bin/bash
# Starts the FastAPI backend on an internal-only port and the Vite dev
# server (the real React frontend) on the artifact's public $PORT.
# Vite proxies /api/* to FastAPI so both are reachable through one service.
set -e
cd "$(dirname "$0")"

FASTAPI_PORT=8001

(cd server_py && PORT="$FASTAPI_PORT" python3 run.py --reload) &
FASTAPI_PID=$!

cleanup() {
  kill "$FASTAPI_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec pnpm exec vite --config vite.config.ts --host 0.0.0.0

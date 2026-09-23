"""Entrypoint used by the artifact's dev/production workflow to start uvicorn.

Reads PORT from the environment (injected by the Replit workflow) instead of
hardcoding a port, and binds to 0.0.0.0 so the shared proxy can reach it.
"""

import argparse
import os

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development.")
    args = parser.parse_args()

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=args.reload)

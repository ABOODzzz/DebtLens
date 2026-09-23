"""
DebtLens FastAPI backend.

Serves the three server-rendered pages (dashboard, login, admin) via Jinja2
templates, and exposes shared dependencies (Firebase auth verification,
Anthropic client) that the rest of the API routes will build on.
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from firebase_client import ADMIN_UID, FIREBASE_ENABLED, get_current_admin, get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debtlens")

# ---------------------------------------------------------------------------
# Anthropic client setup. Used throughout the app for AI-assisted features.
#
# Routed through Replit's AI Integrations proxy (AI_INTEGRATIONS_ANTHROPIC_*),
# so no personal Anthropic API key is required -- usage is billed to Replit
# credits. The model is pinned to claude-sonnet-4-6 for all calls.
# ---------------------------------------------------------------------------
ANTHROPIC_MODEL = "claude-sonnet-4-6"
anthropic_client = None

try:
    from anthropic import Anthropic

    ai_integrations_base_url = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")
    ai_integrations_api_key = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")

    if ai_integrations_base_url and ai_integrations_api_key:
        anthropic_client = Anthropic(
            base_url=ai_integrations_base_url,
            api_key=ai_integrations_api_key,
        )
        logger.info("Anthropic client initialized via Replit AI Integrations proxy.")
    else:
        logger.warning(
            "AI_INTEGRATIONS_ANTHROPIC_BASE_URL / AI_INTEGRATIONS_ANTHROPIC_API_KEY "
            "are not set. AI-assisted features will be unavailable until the "
            "Anthropic AI integration is configured."
        )
except Exception as exc:  # noqa: BLE001
    logger.warning("Failed to initialize Anthropic client: %s", exc)
    anthropic_client = None


# Note: get_current_user / get_current_admin now live in firebase_client.py
# and are imported above. They're kept importable from here indirectly via
# `from firebase_client import get_current_user, get_current_admin` for any
# route modules that need them.

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="DebtLens API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"admin_uid": ADMIN_UID, "firebase_enabled": FIREBASE_ENABLED},
    )


@app.get("/login", response_class=HTMLResponse)
async def read_login(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"firebase_enabled": FIREBASE_ENABLED},
    )


@app.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request):
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"admin_uid": ADMIN_UID, "firebase_enabled": FIREBASE_ENABLED},
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "firebaseEnabled": FIREBASE_ENABLED,
        "anthropicConfigured": anthropic_client is not None,
    }

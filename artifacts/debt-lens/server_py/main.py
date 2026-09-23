"""
DebtLens FastAPI backend.

Serves the three server-rendered pages (dashboard, login, admin) via Jinja2
templates, and exposes shared dependencies (Firebase auth verification,
Anthropic client) that the rest of the API routes will build on.
"""

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debtlens")

# ---------------------------------------------------------------------------
# Fixed admin UID (must match the Firebase project's admin account and the
# ADMIN_UID used elsewhere in the app).
# ---------------------------------------------------------------------------
ADMIN_UID = "f293DyBAsCMK3Tws4no3metSvhB3"

# ---------------------------------------------------------------------------
# Firebase Admin SDK initialization.
#
# The service account credentials are read from the FIREBASE_SERVICE_ACCOUNT_JSON
# environment variable. If it's missing or invalid, we don't crash the app --
# we log a warning and run in a "degraded mode" where any endpoint requiring
# Firebase auth will reject requests with 401 instead of raising an
# unhandled exception at import time.
# ---------------------------------------------------------------------------
firebase_app = None
firebase_auth = None
FIREBASE_ENABLED = False

try:
    import json

    import firebase_admin
    from firebase_admin import auth as firebase_auth_module
    from firebase_admin import credentials

    raw_service_account = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not raw_service_account:
        logger.warning(
            "FIREBASE_SERVICE_ACCOUNT_JSON is not set. Running in degraded mode: "
            "Firebase-authenticated routes will reject all requests with 401."
        )
    else:
        service_account_info = json.loads(raw_service_account)
        cred = credentials.Certificate(service_account_info)
        firebase_app = firebase_admin.initialize_app(cred)
        firebase_auth = firebase_auth_module
        FIREBASE_ENABLED = True
        logger.info("Firebase Admin SDK initialized successfully.")
except Exception as exc:  # noqa: BLE001 - degraded mode must never crash the app
    logger.warning("Failed to initialize Firebase Admin SDK, running in degraded mode: %s", exc)
    firebase_app = None
    firebase_auth = None
    FIREBASE_ENABLED = False

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


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------
def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <token>'.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    return token


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """
    Verify the Firebase ID token from the Authorization header and return the
    decoded token. Raises 401 if the header is missing, malformed, or the
    token fails verification.
    """
    token = _extract_bearer_token(authorization)

    if not FIREBASE_ENABLED or firebase_auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is unavailable: Firebase Admin SDK is not configured.",
        )

    try:
        decoded_token = firebase_auth.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001 - any verification failure is a 401
        logger.info("Firebase ID token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from exc

    return decoded_token


def get_current_admin(decoded_token: dict = Depends(get_current_user)) -> dict:
    """
    Same verification as get_current_user, but additionally requires the
    token's uid to match the fixed admin UID. Raises 403 otherwise.
    """
    if decoded_token.get("uid") != ADMIN_UID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires admin privileges.",
        )
    return decoded_token


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

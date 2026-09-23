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

from anthropic_client import anthropic_client
from api_routes import router as api_router
from firebase_client import ADMIN_UID, FIREBASE_ENABLED, get_current_admin, get_current_user
from admin_routes import router as admin_router
from guarantor import router as guarantor_router
from kyc import router as kyc_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debtlens")

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

app.include_router(api_router)
app.include_router(kyc_router)
app.include_router(admin_router)
app.include_router(guarantor_router)

# ---------------------------------------------------------------------------
# Firebase Web (client-side) config -- these are public app identifiers, not
# secrets in the security sense (Firebase's own docs say so explicitly), but
# they're stored as Replit secrets here because they came in with a VITE_
# prefix. Safe to embed in server-rendered HTML for the client SDK to use.
# ---------------------------------------------------------------------------
FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get("VITE_FIREBASE_API_KEY", ""),
    "authDomain": os.environ.get("VITE_FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.environ.get("VITE_FIREBASE_PROJECT_ID", ""),
    "storageBucket": os.environ.get("VITE_FIREBASE_STORAGE_BUCKET", ""),
    "messagingSenderId": os.environ.get("VITE_FIREBASE_MESSAGING_SENDER_ID", ""),
    "appId": os.environ.get("VITE_FIREBASE_APP_ID", ""),
}
FIREBASE_WEB_CONFIGURED = all(FIREBASE_WEB_CONFIG.values())


@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "admin_uid": ADMIN_UID,
            "firebase_enabled": FIREBASE_ENABLED,
            "firebase_web_config": FIREBASE_WEB_CONFIG,
            "firebase_web_configured": FIREBASE_WEB_CONFIGURED,
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def read_login(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "firebase_enabled": FIREBASE_ENABLED,
            "admin_uid": ADMIN_UID,
            "firebase_web_config": FIREBASE_WEB_CONFIG,
            "firebase_web_configured": FIREBASE_WEB_CONFIGURED,
        },
    )


@app.get("/signup", response_class=HTMLResponse)
async def read_signup(request: Request):
    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            "firebase_enabled": FIREBASE_ENABLED,
            "admin_uid": ADMIN_UID,
            "firebase_web_config": FIREBASE_WEB_CONFIG,
            "firebase_web_configured": FIREBASE_WEB_CONFIGURED,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request):
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "admin_uid": ADMIN_UID,
            "firebase_enabled": FIREBASE_ENABLED,
            "firebase_web_config": FIREBASE_WEB_CONFIG,
            "firebase_web_configured": FIREBASE_WEB_CONFIGURED,
        },
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "firebaseEnabled": FIREBASE_ENABLED,
        "anthropicConfigured": anthropic_client is not None,
    }

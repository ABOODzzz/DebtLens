"""
Firebase Admin SDK setup shared across the app: initialization, the two auth
dependencies (`get_current_user`, `get_current_admin`), and a lazily-created
Firestore client for modules that need to read user data.
"""

import logging
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

logger = logging.getLogger("debtlens")

# ---------------------------------------------------------------------------
# Fixed admin UID (must match the Firebase project's admin account).
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
        storage_bucket = os.environ.get("VITE_FIREBASE_STORAGE_BUCKET")
        firebase_app = firebase_admin.initialize_app(
            cred, options={"storageBucket": storage_bucket} if storage_bucket else None
        )
        firebase_auth = firebase_auth_module
        FIREBASE_ENABLED = True
        logger.info("Firebase Admin SDK initialized successfully.")
except Exception as exc:  # noqa: BLE001 - degraded mode must never crash the app
    logger.warning("Failed to initialize Firebase Admin SDK, running in degraded mode: %s", exc)
    firebase_app = None
    firebase_auth = None
    FIREBASE_ENABLED = False


class FirebaseUnavailableError(RuntimeError):
    """Raised when Firestore/Auth cannot be reached because Firebase Admin is not configured."""


_firestore_client = None


def get_firestore_client():
    """
    Return a lazily-created Firestore client. Raises FirebaseUnavailableError
    if Firebase Admin isn't configured -- callers should translate that into
    a 503, not a missing-data 404.
    """
    global _firestore_client

    if not FIREBASE_ENABLED or firebase_app is None:
        raise FirebaseUnavailableError(
            "Firebase Admin SDK is not configured; cannot read Firestore."
        )

    if _firestore_client is None:
        from firebase_admin import firestore

        _firestore_client = firestore.client(app=firebase_app)

    return _firestore_client


_storage_bucket = None


def get_storage_bucket():
    """
    Return a lazily-created Firebase Storage bucket handle. Raises
    FirebaseUnavailableError if Firebase Admin isn't configured -- callers
    should translate that into a 503, not a missing-data 404.
    """
    global _storage_bucket

    if not FIREBASE_ENABLED or firebase_app is None:
        raise FirebaseUnavailableError(
            "Firebase Admin SDK is not configured; cannot reach Storage."
        )

    if _storage_bucket is None:
        from firebase_admin import storage as firebase_storage

        _storage_bucket = firebase_storage.bucket(app=firebase_app)

    return _storage_bucket


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

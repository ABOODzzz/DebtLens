"""
In-app notifications.

A small, generic notification center backing the Digital Guarantor network:
every time a relationship changes state (request sent, guarantor responds,
admin decides), the affected party gets a notification they can see from the
bell icon in the app header. Kept deliberately simple -- one Firestore
collection, no push/email delivery -- so it's easy to extend to other flows
later (KYC decisions, statement processing, etc.) without a redesign.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from firebase_client import FirebaseUnavailableError, get_current_user, get_firestore_client

logger = logging.getLogger("debtlens")

router = APIRouter(prefix="/api/notifications")

COLLECTION = "notifications"


def _get_db():
    try:
        return get_firestore_client()
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc


def notify(db, *, uid: str, notif_type: str, title: str, message: str, related_id: str | None = None) -> None:
    """Create one notification for `uid`. Best-effort: never raises into the caller's flow."""
    from firebase_admin import firestore

    try:
        db.collection(COLLECTION).document().set(
            {
                "uid": uid,
                "type": notif_type,
                "title": title,
                "message": message,
                "relatedId": related_id,
                "read": False,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
    except Exception as exc:  # noqa: BLE001 - a failed notification must never break the calling flow
        logger.warning("Failed to create notification for uid=%s type=%s: %s", uid, notif_type, exc)


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


@router.get("")
def list_notifications(user: dict = Depends(get_current_user)):
    db = _get_db()
    docs = list(
        db.collection(COLLECTION)
        .where("uid", "==", user["uid"])
        .order_by("createdAt", direction="DESCENDING")
        .limit(50)
        .stream()
    )
    notifications = [
        {
            "id": d.id,
            "type": (d.to_dict() or {}).get("type"),
            "title": (d.to_dict() or {}).get("title"),
            "message": (d.to_dict() or {}).get("message"),
            "related_id": (d.to_dict() or {}).get("relatedId"),
            "read": bool((d.to_dict() or {}).get("read")),
            "created_at": _iso((d.to_dict() or {}).get("createdAt")),
        }
        for d in docs
    ]
    return {
        "notifications": notifications,
        "unread_count": sum(1 for n in notifications if not n["read"]),
    }


class MarkReadBody(BaseModel):
    notification_id: str


@router.post("/mark-read")
def mark_read(body: MarkReadBody, user: dict = Depends(get_current_user)):
    db = _get_db()
    ref = db.collection(COLLECTION).document(body.notification_id)
    snapshot = ref.get()
    if not snapshot.exists or (snapshot.to_dict() or {}).get("uid") != user["uid"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    ref.update({"read": True})
    return {"id": body.notification_id, "read": True}


@router.post("/mark-all-read")
def mark_all_read(user: dict = Depends(get_current_user)):
    db = _get_db()
    docs = list(db.collection(COLLECTION).where("uid", "==", user["uid"]).where("read", "==", False).stream())
    for d in docs:
        d.reference.update({"read": True})
    return {"marked_count": len(docs)}

"""
Digital Guarantor (الكفيل الرقمي) network.

Lets any already-verified, good-standing DebtLens customer vouch for one or
more other customers, up to a small backed amount each -- directly targeting
the "guarantor_needed" gap flagged by finance.assess_eligibility for
applicants who don't have a traditional bank guarantor.

This is a many-to-many network, not a single link: a customer can have
several guarantors backing them, and a guarantor can back several customers
at once, each relationship capped individually and the guarantor's total
exposure capped in aggregate.

Every guarantor relationship lives in its own document in the
`guarantorRelationships` collection (never as a single field on a user doc),
so the same two people can have at most one *active* relationship at a time,
but any number of people can be linked to any number of others.

Flow per relationship:
1. The applicant (who needs a guarantor) requests a specific person by
   national ID. Rejected up front if the guarantor is unverified, in poor
   financial standing, or already at capacity.
2. The named guarantor sees the pending request and approves or declines.
   Approval does NOT immediately activate the guarantee -- it only raises
   the request to "awaiting_admin_review".
3. An admin reviews both parties' identity and financial standing (with an
   AI-assisted comparison) and makes the final approve/reject call in
   admin_routes.py. Only an "approved" relationship counts toward the
   applicant's loan assessment boost (see api_routes.py's
   _guarantor_context), and only after re-validating the guarantor is still
   in good standing -- a stale approval is never trusted.

Every step that changes a relationship's status fires an in-app notification
(see notifications.py) to the other party so nothing sits silently.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from firebase_client import FirebaseUnavailableError, get_current_user, get_firestore_client
from notifications import notify
from user_data import get_user_financial_profile

logger = logging.getLogger("debtlens")

router = APIRouter(prefix="/api/guarantor")

# A guarantor's own debt burden must be reasonably low, or their backing is
# worthless -- and the amount any single digital guarantor can stand behind
# per relationship is capped small on purpose, since there's no legal
# recourse here, just a soft credibility signal fed to the AI assessment.
GUARANTOR_MAX_DTI_PERCENT = 40.0
GUARANTOR_BACKED_MAX_AMOUNT = 500.0  # JOD, per relationship

# Network-wide caps so no single account becomes an unbounded hub. A
# guarantor's total exposure is derived from the per-relationship cap so the
# two numbers can never drift apart.
GUARANTOR_MAX_CONCURRENT = 3  # a guarantor can back at most this many people at once
GUARANTOR_MAX_TOTAL_EXPOSURE = GUARANTOR_MAX_CONCURRENT * GUARANTOR_BACKED_MAX_AMOUNT

# An applicant can likewise line up at most this many guarantors backing them
# at the same time.
REQUESTER_MAX_GUARANTORS = 3
REQUESTER_MAX_TOTAL_BACKED = REQUESTER_MAX_GUARANTORS * GUARANTOR_BACKED_MAX_AMOUNT

# Statuses that count against a person's capacity -- still "live" in some
# sense, either using up a slot or actively backing a loan.
_ACTIVE_STATUSES = ("pending", "awaiting_admin_review", "approved")

COLLECTION = "guarantorRelationships"


def _get_db():
    try:
        return get_firestore_client()
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc


def _get_user_doc(db, uid: str) -> dict:
    snapshot = db.collection("users").document(uid).get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No user found for uid={uid}")
    return snapshot.to_dict() or {}


def _display_name(user_doc: dict) -> str:
    kyc = user_doc.get("kycVerification") or {}
    return kyc.get("typedFullName") or kyc.get("extractedFullName") or "عميل"


def _find_uid_by_national_id(db, national_id: str) -> str | None:
    """
    Look up a user by their self-reported national ID. Checked against the
    top-level `nationalId` field written at KYC submission time.
    """
    matches = list(db.collection("users").where("nationalId", "==", national_id).limit(1).stream())
    return matches[0].id if matches else None


def _relationships_for(db, field: str, uid: str) -> list[dict]:
    """All guarantorRelationships docs where `field` == uid, each tagged with its doc id."""
    out = []
    for snap in db.collection(COLLECTION).where(field, "==", uid).stream():
        data = snap.to_dict() or {}
        data["id"] = snap.id
        out.append(data)
    return out


def _capacity(db, field: str, uid: str, max_count: int, max_amount: float) -> dict:
    """
    How much of this person's network capacity (as either guarantor or
    requester) is currently used by active relationships.
    """
    active = [r for r in _relationships_for(db, field, uid) if r.get("status") in _ACTIVE_STATUSES]
    used_amount = sum(r.get("maxAmount") or 0 for r in active)
    return {
        "used_count": len(active),
        "max_count": max_count,
        "used_amount": used_amount,
        "max_amount": max_amount,
    }


def get_active_guarantors_for(uid: str) -> list[dict]:
    """
    Approved, still-active guarantor relationships backing this applicant.
    Used by api_routes.py to compute the loan-assessment boost. Each
    guarantor's current standing must still be re-checked by the caller --
    "approved" here only means an admin approved it at some point in the
    past, not that it's still safe to rely on today.
    """
    try:
        db = get_firestore_client()
    except FirebaseUnavailableError:
        return []
    return [r for r in _relationships_for(db, "requesterUid", uid) if r.get("status") == "approved"]


def _relationship_summary(db, rel: dict) -> dict:
    requester_doc = db.collection("users").document(rel["requesterUid"]).get()
    guarantor_doc = db.collection("users").document(rel["guarantorUid"]).get()
    requester_name = _display_name(requester_doc.to_dict() or {}) if requester_doc.exists else "عميل"
    guarantor_name = _display_name(guarantor_doc.to_dict() or {}) if guarantor_doc.exists else "عميل"
    return {
        "id": rel["id"],
        "requester_uid": rel["requesterUid"],
        "requester_name": requester_name,
        "guarantor_uid": rel["guarantorUid"],
        "guarantor_name": guarantor_name,
        "status": rel.get("status"),
        "max_amount": rel.get("maxAmount"),
        "requested_at": _iso(rel.get("requestedAt")),
        "responded_at": _iso(rel.get("respondedAt")),
        "admin_decision_reason": rel.get("adminDecisionReason"),
    }


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


class GuarantorRequestBody(BaseModel):
    guarantor_national_id: str


@router.post("/request")
def request_guarantor(body: GuarantorRequestBody, user: dict = Depends(get_current_user)):
    requester_uid = user["uid"]
    db = _get_db()

    guarantor_uid = _find_uid_by_national_id(db, body.guarantor_national_id)
    if not guarantor_uid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="لم يتم العثور على عميل مسجل بهذا الرقم الوطني.",
        )
    if guarantor_uid == requester_uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot be your own guarantor.")

    # No duplicate active relationship between the same pair.
    existing = [
        r
        for r in _relationships_for(db, "requesterUid", requester_uid)
        if r.get("guarantorUid") == guarantor_uid and r.get("status") in _ACTIVE_STATUSES
    ]
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لديك بالفعل طلب كفالة نشط مع هذا الشخص.",
        )

    try:
        guarantor_profile = get_user_financial_profile(guarantor_uid)
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc

    if guarantor_profile["data_source"] != "verified":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This person doesn't have verified statements yet, so they can't act as a digital guarantor.",
        )

    dti = guarantor_profile["debt_to_income_percentage"]
    if guarantor_profile["stacking_flag"] or (dti is not None and dti >= GUARANTOR_MAX_DTI_PERCENT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This person's own debt load is too high to act as a digital guarantor right now.",
        )

    # Network capacity checks -- neither side of the relationship may exceed
    # its concurrent-guarantee or total-exposure limits.
    guarantor_capacity = _capacity(db, "guarantorUid", guarantor_uid, GUARANTOR_MAX_CONCURRENT, GUARANTOR_MAX_TOTAL_EXPOSURE)
    if guarantor_capacity["used_count"] >= GUARANTOR_MAX_CONCURRENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"هذا الشخص يكفل بالفعل الحد الأقصى المسموح به ({GUARANTOR_MAX_CONCURRENT} أشخاص).",
        )
    if guarantor_capacity["used_amount"] + GUARANTOR_BACKED_MAX_AMOUNT > GUARANTOR_MAX_TOTAL_EXPOSURE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"هذا الشخص وصل للحد الأقصى لإجمالي مبالغ الكفالة ({GUARANTOR_MAX_TOTAL_EXPOSURE:.0f} د.أ).",
        )

    requester_capacity = _capacity(db, "requesterUid", requester_uid, REQUESTER_MAX_GUARANTORS, REQUESTER_MAX_TOTAL_BACKED)
    if requester_capacity["used_count"] >= REQUESTER_MAX_GUARANTORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"لديك بالفعل الحد الأقصى من طلبات/كفالات الكفلاء ({REQUESTER_MAX_GUARANTORS}).",
        )

    from firebase_admin import firestore

    now = firestore.SERVER_TIMESTAMP
    requester_doc = _get_user_doc(db, requester_uid)
    guarantor_doc = _get_user_doc(db, guarantor_uid)
    requester_name = _display_name(requester_doc)
    guarantor_name = _display_name(guarantor_doc)

    relationship_ref = db.collection(COLLECTION).document()
    relationship_ref.set(
        {
            "requesterUid": requester_uid,
            "requesterName": requester_name,
            "requesterNationalId": requester_doc.get("nationalId"),
            "guarantorUid": guarantor_uid,
            "guarantorName": guarantor_name,
            "guarantorNationalId": guarantor_doc.get("nationalId"),
            "status": "pending",
            "maxAmount": GUARANTOR_BACKED_MAX_AMOUNT,
            "requestedAt": now,
            "respondedAt": None,
            "adminDecisionAt": None,
            "adminDecisionReason": None,
        }
    )

    notify(
        db,
        uid=guarantor_uid,
        notif_type="guarantor_request_received",
        title="طلب كفالة رقمية جديد",
        message=f"{requester_name} يطلب منك أن تكون كفيله الرقمي بحد أقصى {GUARANTOR_BACKED_MAX_AMOUNT:.0f} د.أ.",
        related_id=relationship_ref.id,
    )

    return {
        "id": relationship_ref.id,
        "status": "pending",
        "guarantor_uid": guarantor_uid,
        "guarantor_name": guarantor_name,
        "max_amount": GUARANTOR_BACKED_MAX_AMOUNT,
    }


class GuarantorRespondBody(BaseModel):
    relationship_id: str
    approve: bool


@router.post("/respond")
def respond_to_guarantor_request(body: GuarantorRespondBody, user: dict = Depends(get_current_user)):
    guarantor_uid = user["uid"]
    db = _get_db()

    relationship_ref = db.collection(COLLECTION).document(body.relationship_id)
    snapshot = relationship_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guarantor request not found.")
    rel = snapshot.to_dict() or {}

    if rel.get("guarantorUid") != guarantor_uid or rel.get("status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending guarantor request naming you as guarantor with this id.",
        )

    from firebase_admin import firestore

    # Approving here only raises the request to "awaiting_admin_review" --
    # the guarantee only becomes active once an admin makes the final call
    # (see admin_routes.py's /guarantor-decision), after reviewing both
    # parties' identity and financial standing.
    new_status = "awaiting_admin_review" if body.approve else "declined"
    relationship_ref.update(
        {
            "status": new_status,
            "respondedAt": firestore.SERVER_TIMESTAMP,
        }
    )

    guarantor_name = rel.get("guarantorName") or "الكفيل"
    if body.approve:
        notify(
            db,
            uid=rel["requesterUid"],
            notif_type="guarantor_accepted",
            title="وافق الكفيل على طلبك",
            message=f"{guarantor_name} وافق على أن يكون كفيلك الرقمي، والطلب الآن بانتظار مراجعة الإدارة.",
            related_id=body.relationship_id,
        )
    else:
        notify(
            db,
            uid=rel["requesterUid"],
            notif_type="guarantor_declined",
            title="رفض الكفيل طلبك",
            message=f"{guarantor_name} اعتذر عن أن يكون كفيلك الرقمي.",
            related_id=body.relationship_id,
        )

    return {"id": body.relationship_id, "requester_uid": rel["requesterUid"], "status": new_status}


@router.get("/network")
def guarantor_network(user: dict = Depends(get_current_user)):
    uid = user["uid"]
    db = _get_db()

    outgoing = sorted(
        _relationships_for(db, "requesterUid", uid),
        key=lambda r: r.get("requestedAt") or 0,
        reverse=True,
    )
    incoming = sorted(
        _relationships_for(db, "guarantorUid", uid),
        key=lambda r: r.get("requestedAt") or 0,
        reverse=True,
    )

    return {
        "outgoing": [_relationship_summary(db, r) for r in outgoing],
        "incoming": [_relationship_summary(db, r) for r in incoming],
        "guarantor_capacity": _capacity(db, "guarantorUid", uid, GUARANTOR_MAX_CONCURRENT, GUARANTOR_MAX_TOTAL_EXPOSURE),
        "requester_capacity": _capacity(db, "requesterUid", uid, REQUESTER_MAX_GUARANTORS, REQUESTER_MAX_TOTAL_BACKED),
    }

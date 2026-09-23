"""
Digital Guarantor (الكفيل الرقمي).

Lets an already-verified, good-standing DebtLens customer vouch for a
second customer up to a small backed amount -- directly targeting the
"guarantor_needed" gap flagged by finance.assess_eligibility for applicants
who don't have a traditional bank guarantor.

Flow:
1. The applicant (who needs a guarantor) requests a specific person by uid.
2. The request is only accepted if that person is themselves verified and
   in good financial standing -- a shaky guarantor helps no one.
3. The named guarantor sees the pending request and approves or declines.
4. Once approved, users/{applicant_uid}.guarantorUid is set. The AI loan
   assessment endpoint (api_routes.py) picks this up, relaxes the
   debt-to-income ceiling, and asks Claude to consider a better rate --
   capped by GUARANTOR_BACKED_MAX_AMOUNT so this never turns into an
   unbounded co-signed loan.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from firebase_client import FirebaseUnavailableError, get_current_user, get_firestore_client
from user_data import get_user_financial_profile

logger = logging.getLogger("debtlens")

router = APIRouter(prefix="/api/guarantor")

# A guarantor's own debt burden must be reasonably low, or their backing is
# worthless -- and the amount any single digital guarantor can stand behind
# is capped small on purpose, since there's no legal recourse here, just a
# soft credibility signal fed to the AI assessment.
GUARANTOR_MAX_DTI_PERCENT = 40.0
GUARANTOR_BACKED_MAX_AMOUNT = 500.0  # JOD


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


class GuarantorRequestBody(BaseModel):
    guarantor_uid: str


@router.post("/request")
def request_guarantor(body: GuarantorRequestBody, user: dict = Depends(get_current_user)):
    requester_uid = user["uid"]
    if body.guarantor_uid == requester_uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot be your own guarantor.")

    db = _get_db()
    _get_user_doc(db, body.guarantor_uid)  # 404s if that person doesn't exist

    try:
        guarantor_profile = get_user_financial_profile(body.guarantor_uid)
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

    from firebase_admin import firestore

    now = firestore.SERVER_TIMESTAMP
    requester_ref = db.collection("users").document(requester_uid)
    guarantor_ref = db.collection("users").document(body.guarantor_uid)

    requester_ref.set(
        {
            "guarantorRequest": {
                "guarantorUid": body.guarantor_uid,
                "status": "pending",
                "requestedAt": now,
                "respondedAt": None,
                "maxAmount": GUARANTOR_BACKED_MAX_AMOUNT,
            },
        },
        merge=True,
    )

    guarantor_ref.set(
        {
            "incomingGuarantorRequests": {
                requester_uid: {
                    "status": "pending",
                    "requestedAt": now,
                    "maxAmount": GUARANTOR_BACKED_MAX_AMOUNT,
                },
            },
        },
        merge=True,
    )

    return {
        "status": "pending",
        "guarantor_uid": body.guarantor_uid,
        "max_amount": GUARANTOR_BACKED_MAX_AMOUNT,
    }


class GuarantorRespondBody(BaseModel):
    requester_uid: str
    approve: bool


@router.post("/respond")
def respond_to_guarantor_request(body: GuarantorRespondBody, user: dict = Depends(get_current_user)):
    guarantor_uid = user["uid"]
    db = _get_db()

    requester_doc_ref = db.collection("users").document(body.requester_uid)
    requester_doc = _get_user_doc(db, body.requester_uid)

    pending = requester_doc.get("guarantorRequest") or {}
    if pending.get("guarantorUid") != guarantor_uid or pending.get("status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending guarantor request from this user naming you as guarantor.",
        )

    from firebase_admin import firestore

    new_status = "approved" if body.approve else "declined"
    update = {
        "guarantorRequest.status": new_status,
        "guarantorRequest.respondedAt": firestore.SERVER_TIMESTAMP,
    }
    if body.approve:
        update["guarantorUid"] = guarantor_uid
    requester_doc_ref.update(update)

    db.collection("users").document(guarantor_uid).update(
        {f"incomingGuarantorRequests.{body.requester_uid}.status": new_status}
    )

    return {"requester_uid": body.requester_uid, "status": new_status}


@router.get("/status")
def guarantor_status(user: dict = Depends(get_current_user)):
    db = _get_db()
    doc = _get_user_doc(db, user["uid"])
    return {
        "outgoing_request": doc.get("guarantorRequest"),
        "approved_guarantor_uid": doc.get("guarantorUid"),
        "incoming_requests": doc.get("incomingGuarantorRequests") or {},
    }

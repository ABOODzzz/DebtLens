"""
Digital Guarantor (الكفيل الرقمي).

Lets an already-verified, good-standing DebtLens customer vouch for a
second customer up to a small backed amount -- directly targeting the
"guarantor_needed" gap flagged by finance.assess_eligibility for applicants
who don't have a traditional bank guarantor.

Flow:
1. The applicant (who needs a guarantor) requests a specific person by
   national ID.
2. The request is only accepted if that person is themselves verified and
   in good financial standing -- a shaky guarantor helps no one.
3. The named guarantor sees the pending request and approves or declines.
   Approval does NOT immediately activate the guarantee -- it only raises
   the request to "awaiting_admin_review".
4. An admin reviews both parties' identity and financial standing (with an
   AI-assisted comparison) and makes the final call in admin_routes.py.
   Only then is users/{applicant_uid}.guarantorUid set. The AI loan
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
    guarantor_national_id: str


def _find_uid_by_national_id(db, national_id: str) -> str | None:
    """
    Look up a user by their self-reported national ID. Checked against the
    top-level `nationalId` field written at KYC submission time.
    """
    matches = list(
        db.collection("users").where("nationalId", "==", national_id).limit(1).stream()
    )
    return matches[0].id if matches else None


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

    from firebase_admin import firestore

    now = firestore.SERVER_TIMESTAMP
    requester_ref = db.collection("users").document(requester_uid)
    guarantor_ref = db.collection("users").document(guarantor_uid)
    guarantor_doc = _get_user_doc(db, guarantor_uid)
    guarantor_kyc = guarantor_doc.get("kycVerification") or {}
    guarantor_name = guarantor_kyc.get("typedFullName") or guarantor_kyc.get("extractedFullName") or "الكفيل"

    requester_ref.set(
        {
            "guarantorRequest": {
                "guarantorUid": guarantor_uid,
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
        "guarantor_uid": guarantor_uid,
        "guarantor_name": guarantor_name,
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

    # Approving here only raises the request to "awaiting_admin_review" --
    # the guarantee only becomes active once an admin makes the final call
    # (see admin_routes.py's /guarantor-decision), after reviewing both
    # parties' identity and financial standing.
    new_status = "awaiting_admin_review" if body.approve else "declined"
    update = {
        "guarantorRequest.status": new_status,
        "guarantorRequest.respondedAt": firestore.SERVER_TIMESTAMP,
    }
    requester_doc_ref.update(update)

    db.collection("users").document(guarantor_uid).update(
        {f"incomingGuarantorRequests.{body.requester_uid}.status": new_status}
    )

    return {"requester_uid": body.requester_uid, "status": new_status}


def _display_name(user_doc: dict) -> str:
    kyc = user_doc.get("kycVerification") or {}
    return kyc.get("typedFullName") or kyc.get("extractedFullName") or "عميل"


@router.get("/status")
def guarantor_status(user: dict = Depends(get_current_user)):
    db = _get_db()
    doc = _get_user_doc(db, user["uid"])

    outgoing_request = doc.get("guarantorRequest")
    if outgoing_request and outgoing_request.get("guarantorUid"):
        guarantor_snapshot = db.collection("users").document(outgoing_request["guarantorUid"]).get()
        if guarantor_snapshot.exists:
            outgoing_request = {**outgoing_request, "guarantorName": _display_name(guarantor_snapshot.to_dict() or {})}

    incoming_requests_raw = doc.get("incomingGuarantorRequests") or {}
    incoming_requests = {}
    for requester_uid, request in incoming_requests_raw.items():
        requester_snapshot = db.collection("users").document(requester_uid).get()
        requester_name = _display_name(requester_snapshot.to_dict() or {}) if requester_snapshot.exists else "عميل"
        incoming_requests[requester_uid] = {**request, "requesterName": requester_name}

    return {
        "outgoing_request": outgoing_request,
        "approved_guarantor_uid": doc.get("guarantorUid"),
        "incoming_requests": incoming_requests,
    }

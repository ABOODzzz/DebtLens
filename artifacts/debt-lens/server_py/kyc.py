"""
KYC (identity verification) submission endpoint.

Flow:
1. Client uploads an ID front photo and a selfie somewhere (object storage,
   etc.) and POSTs the resulting URLs here, along with the name they typed
   during onboarding and an optional national ID number.
2. We download both images server-side and send them to Claude in a single
   vision request, asking it to compare the face in both photos, read the
   name/national ID off the ID document, and judge photo quality.
3. We apply a strict, server-side decision policy on top of that verdict --
   the client never gets to set or influence `reviewStatus` directly, since
   it only ever sends photo URLs and typed text, never a status.
4. The decision, the full AI verdict, and an audit log entry are written to
   Firestore before anything is returned to the client.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from anthropic_client import ANTHROPIC_MODEL, anthropic_client
from firebase_client import (
    FirebaseUnavailableError,
    get_current_user,
    get_firestore_client,
    get_storage_bucket,
)

logger = logging.getLogger("debtlens")

router = APIRouter(prefix="/api/kyc")

_IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 15
_MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB, generous for a phone photo
_ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
# This is a face-comparison + document-reading vision task, so it gets a
# larger token budget than the plain-text endpoints.
_KYC_MAX_TOKENS = 16000


class KycProfileInput(BaseModel):
    fullName: str
    nationalId: str | None = None


class KycSubmitRequest(BaseModel):
    profile: KycProfileInput
    photoPaths: list[str]  # [idFrontPath, idBackPath, selfiePath] -- Firebase Storage paths


def _download_storage_image(path: str) -> tuple[bytes, str] | None:
    """
    Download an image from Firebase Storage by path and return
    (bytes, media_type). Returns None on any failure (missing blob, storage
    unavailable, empty body, too large) -- callers treat that as "download
    failed" and fall back to pending review.
    """
    try:
        bucket = get_storage_bucket()
        blob = bucket.blob(path)
        if not blob.exists():
            logger.warning("KYC image blob does not exist: %s", path)
            return None
        content = blob.download_as_bytes()
    except FirebaseUnavailableError as exc:
        logger.warning("KYC image download failed for %s: %s", path, exc)
        return None
    except Exception as exc:  # noqa: BLE001 - any storage failure is a soft failure here
        logger.warning("KYC image download failed for %s: %s", path, exc)
        return None

    if not content or len(content) > _MAX_IMAGE_BYTES:
        logger.warning("KYC image at %s is empty or too large (%s bytes)", path, len(content or b""))
        return None

    media_type = (blob.content_type or "").split(";")[0].strip().lower()
    if media_type not in _ALLOWED_MEDIA_TYPES:
        # Best-effort guess when Storage didn't record a usable content type.
        media_type = "image/jpeg"

    return content, media_type


def _extract_response_text(message) -> str:
    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip()


def _parse_verdict_json(text: str) -> dict:
    """Parse Claude's verdict, tolerating markdown code fences around the JSON."""
    import json

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))

    if not isinstance(data, dict):
        raise ValueError("Verdict JSON is not an object")

    required_str_fields = ["face_match", "confidence", "reason"]
    for field in required_str_fields:
        if not isinstance(data.get(field), str):
            raise ValueError(f"Missing or invalid '{field}' in verdict JSON")

    for field in ["id_photo_readable", "selfie_readable"]:
        if not isinstance(data.get(field), bool):
            raise ValueError(f"Missing or invalid '{field}' in verdict JSON")

    # Optional, nullable fields.
    data.setdefault("extracted_full_name", None)
    data.setdefault("extracted_national_id", None)

    return data


def _request_kyc_verdict(id_photo: tuple[bytes, str], selfie: tuple[bytes, str]) -> dict:
    import base64

    id_bytes, id_media_type = id_photo
    selfie_bytes, selfie_media_type = selfie

    prompt = """أنت نظام تحقق من الهوية. ستُعطى صورتين: الأولى لبطاقة هوية، والثانية لصورة سيلفي شخصية.

المطلوب:
1. قارن الوجه الظاهر في صورة الهوية مع الوجه في صورة السيلفي.
2. اقرأ الاسم الكامل ورقم الهوية الوطنية من صورة بطاقة الهوية إن كانا واضحين.
3. قيّم ما إذا كانت كل صورة واضحة وقابلة للاستخدام فعليًا (ليست ضبابية، غير مقصوصة، إضاءة كافية، لا انعكاسات تحجب المعلومات).

أعد ردك بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، وبالضبط بالشكل التالي:
{
  "face_match": "match" | "no_match" | "uncertain",
  "confidence": "high" | "medium" | "low",
  "reason": "شرح موجز لقرارك",
  "id_photo_readable": true | false,
  "selfie_readable": true | false,
  "extracted_full_name": "الاسم كما يظهر في الهوية أو null إذا غير واضح",
  "extracted_national_id": "رقم الهوية الوطنية كما يظهر أو null إذا غير واضح"
}"""

    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": "الصورة الأولى: بطاقة الهوية."},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": id_media_type,
                "data": base64.b64encode(id_bytes).decode("ascii"),
            },
        },
        {"type": "text", "text": "الصورة الثانية: صورة السيلفي."},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": selfie_media_type,
                "data": base64.b64encode(selfie_bytes).decode("ascii"),
            },
        },
    ]

    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=_KYC_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    text = _extract_response_text(message)
    return _parse_verdict_json(text)


# ---------------------------------------------------------------------------
# Fuzzy (token-overlap) name matching -- deliberately not an exact string
# match, since ID documents often include a middle/father's name that the
# user didn't type, or minor transliteration differences.
# ---------------------------------------------------------------------------
_ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_ALEF_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})

_NAME_MATCH_OVERLAP_THRESHOLD = 0.6


def _normalize_name_tokens(name: str | None) -> set[str]:
    if not name:
        return set()
    cleaned = _ARABIC_DIACRITICS_RE.sub("", name)
    cleaned = cleaned.translate(_ALEF_VARIANTS)
    cleaned = _NON_WORD_RE.sub(" ", cleaned)
    return {token for token in cleaned.lower().split() if token}


def _names_reasonably_match(typed_name: str, extracted_name: str | None) -> bool:
    typed_tokens = _normalize_name_tokens(typed_name)
    extracted_tokens = _normalize_name_tokens(extracted_name)

    if not typed_tokens or not extracted_tokens:
        return False

    overlap = typed_tokens & extracted_tokens
    smaller_side = min(len(typed_tokens), len(extracted_tokens))
    return (len(overlap) / smaller_side) >= _NAME_MATCH_OVERLAP_THRESHOLD


def _decide_review(typed_full_name: str, verdict: dict) -> tuple[str, str]:
    """
    Apply the server-side approval policy. Returns (review_status, reason).
    review_status is either "approved" or "pending" -- this endpoint never
    auto-rejects, it only fast-tracks clear matches and routes everything
    else to manual review.
    """
    face_match = verdict["face_match"]
    confidence = verdict["confidence"]
    id_readable = verdict["id_photo_readable"]
    selfie_readable = verdict["selfie_readable"]
    extracted_name = verdict.get("extracted_full_name")
    ai_reason = verdict.get("reason", "")

    quality_ok = id_readable and selfie_readable
    name_match = _names_reasonably_match(typed_full_name, extracted_name)

    if face_match == "match" and confidence == "high" and quality_ok and name_match:
        return (
            "approved",
            "تمت الموافقة تلقائيًا: تطابق الوجه بثقة عالية، وتطابق الاسم مع الهوية، "
            "وجودة الصورتين مقبولة.",
        )

    issues = []
    if face_match != "match":
        issues.append(f"نتيجة مطابقة الوجه: {face_match}")
    if confidence != "high":
        issues.append(f"مستوى الثقة: {confidence}")
    if not quality_ok:
        unreadable = []
        if not id_readable:
            unreadable.append("صورة الهوية")
        if not selfie_readable:
            unreadable.append("صورة السيلفي")
        issues.append(f"جودة غير كافية في: {', '.join(unreadable)}")
    if not name_match:
        issues.append(
            f"الاسم المستخرج ('{extracted_name or 'غير واضح'}') لا يتطابق بشكل كافٍ "
            f"مع الاسم المدخل ('{typed_full_name}')"
        )

    note = "بانتظار المراجعة اليدوية. " + "؛ ".join(issues) + "."
    if ai_reason:
        note += f" ملاحظة الذكاء الاصطناعي: {ai_reason}"

    return "pending", note


@router.get("/status")
def kyc_status(user: dict = Depends(get_current_user)):
    """
    Let the logged-in customer check their own identity-verification status.
    Never exposes another user's data -- always reads users/{current uid}.
    """
    try:
        db = get_firestore_client()
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc

    snapshot = db.collection("users").document(user["uid"]).get()
    user_doc = snapshot.to_dict() or {} if snapshot.exists else {}

    return {
        "has_submission": bool(user_doc.get("kycVerification")),
        "review_status": user_doc.get("reviewStatus") or "no_submission",
        "review_reason": user_doc.get("reviewReason"),
    }


@router.post("/submit")
def submit_kyc(body: KycSubmitRequest, user: dict = Depends(get_current_user)):
    uid = user["uid"]

    if len(body.photoPaths) != 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="photoPaths must contain exactly 3 entries: [idFrontPath, idBackPath, selfiePath].",
        )
    id_front_path, id_back_path, selfie_path = body.photoPaths
    full_name = body.profile.fullName
    national_id = body.profile.nationalId

    if anthropic_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity verification is currently unavailable.",
        )

    id_photo = _download_storage_image(id_front_path)
    selfie = _download_storage_image(selfie_path)

    verdict: dict | None = None
    verdict_error: str | None = None

    if id_photo is None or selfie is None:
        review_status = "pending"
        review_reason = "تعذر تحميل إحدى صورتي التحقق (الهوية أو السيلفي)؛ الحالة قيد المراجعة اليدوية."
        verdict_error = "image_download_failed"
    else:
        try:
            verdict = _request_kyc_verdict(id_photo, selfie)
        except Exception as exc:  # noqa: BLE001 - any AI/parse failure falls back to pending
            logger.error("KYC verdict generation failed for uid=%s: %s", uid, exc)
            review_status = "pending"
            review_reason = "تعذر إتمام التحقق الآلي من الهوية؛ الحالة قيد المراجعة اليدوية."
            verdict_error = "verdict_generation_failed"
        else:
            review_status, review_reason = _decide_review(full_name, verdict)

    try:
        db = get_firestore_client()
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc

    from firebase_admin import firestore

    user_doc_ref = db.collection("users").document(uid)
    kyc_verification = {
        "typedFullName": full_name,
        "typedNationalId": national_id,
        "idFrontPath": id_front_path,
        "idBackPath": id_back_path,
        "selfiePath": selfie_path,
        "faceMatch": verdict["face_match"] if verdict else None,
        "confidence": verdict["confidence"] if verdict else None,
        "aiReason": verdict.get("reason") if verdict else None,
        "idPhotoReadable": verdict["id_photo_readable"] if verdict else None,
        "selfieReadable": verdict["selfie_readable"] if verdict else None,
        "extractedFullName": verdict.get("extracted_full_name") if verdict else None,
        "extractedNationalId": verdict.get("extracted_national_id") if verdict else None,
        "error": verdict_error,
        "verifiedAt": firestore.SERVER_TIMESTAMP,
    }

    user_doc_ref.set(
        {
            "reviewStatus": review_status,
            "reviewReason": review_reason,
            "kycVerification": kyc_verification,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    user_doc_ref.collection("kycAuditLog").add(
        {
            "uid": uid,
            "reviewStatus": review_status,
            "reviewReason": review_reason,
            "typedFullName": full_name,
            "typedNationalId": national_id,
            "verdict": verdict,
            "error": verdict_error,
            "createdAt": firestore.SERVER_TIMESTAMP,
        }
    )

    return {
        "reviewStatus": review_status,
        "reason": review_reason,
    }

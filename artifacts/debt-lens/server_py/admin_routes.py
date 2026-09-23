"""
Admin-only endpoints backing the admin.html review dashboard.

Covers:
- POST /analyze-statement: turns an already-uploaded bank/loan statement
  file (PDF or image) into structured, Firestore-ready financial data.
- POST /institution-request: drafts a formal letter to a lender/bank asking
  for a user's full loan/account details.
- POST /bank-request: same idea, but first runs a Claude vision call on the
  user's on-file ID photo to confirm identity, then lists specific bank
  accounts in the letter.
- POST /user-insight: internal risk-tier note for the review team on one
  pending user.
- POST /portfolio-summary: ranks a batch of pending users by review
  priority with a one-line explanation each.

All Claude calls go through the same Anthropic client used elsewhere in the
app, and any JSON response that doesn't parse gets one repair pass that
fixes syntax only, never inventing data.
"""

import base64
import json
import logging
import re
from typing import Literal

import requests
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from anthropic_client import ANTHROPIC_MODEL, anthropic_client
from firebase_client import FirebaseUnavailableError, get_current_admin, get_firestore_client
from user_data import get_user_financial_profile

logger = logging.getLogger("debtlens")

router = APIRouter(prefix="/api/admin")

_FILE_DOWNLOAD_TIMEOUT_SECONDS = 30
_MAX_FILE_BYTES = 32 * 1024 * 1024  # 32 MB
# Statements can run long (many pages, many transactions), so this gets a
# generous output budget -- same as the other AI-vision endpoint (KYC).
_STATEMENT_MAX_TOKENS = 16000
_JSON_FIX_MAX_TOKENS = 16000

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_BANK_CATEGORIES = ["transfers", "food", "shopping", "cash_withdrawal", "bills", "salary", "other"]


class AnalyzeStatementRequest(BaseModel):
    uid: str
    institution_name: str
    institution_type: Literal["bank", "financing"]
    file_url: str


# ---------------------------------------------------------------------------
# File download + Claude content block
# ---------------------------------------------------------------------------
def _download_file(url: str) -> tuple[bytes, str] | None:
    try:
        response = requests.get(url, timeout=_FILE_DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any network failure is a soft failure here
        logger.warning("Statement file download failed for %s: %s", url, exc)
        return None

    content = response.content
    if not content or len(content) > _MAX_FILE_BYTES:
        logger.warning(
            "Statement file at %s is empty or too large (%s bytes)", url, len(content or b"")
        )
        return None

    media_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    lowered_url = url.lower().split("?")[0]

    if media_type == "application/pdf" or lowered_url.endswith(".pdf"):
        media_type = "application/pdf"
    elif media_type in _ALLOWED_IMAGE_TYPES:
        pass
    elif lowered_url.endswith(".png"):
        media_type = "image/png"
    elif lowered_url.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif lowered_url.endswith(".webp"):
        media_type = "image/webp"
    elif lowered_url.endswith(".gif"):
        media_type = "image/gif"
    else:
        # Statements are more often PDFs than unlabeled images.
        media_type = "application/pdf"

    return content, media_type


def _file_content_block(file_bytes: bytes, media_type: str) -> dict:
    data_b64 = base64.b64encode(file_bytes).decode("ascii")
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": data_b64},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data_b64},
    }


def _extract_response_text(message) -> str:
    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# JSON parsing with a Claude-powered repair pass
# ---------------------------------------------------------------------------
def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _try_parse_json(text: str) -> dict | None:
    cleaned = _strip_json_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _fix_json_via_claude(broken_text: str) -> dict | None:
    """
    Second-pass call: ask Claude to fix JSON *syntax* only (missing braces,
    stray/missing commas, unescaped quotes, truncation, etc.) without
    inventing or altering any data.
    """
    prompt = f"""فيما يلي رد كان يُفترض أن يكون كائن JSON صالحًا، لكنه يحتوي على خطأ في صياغة الـ JSON فقط:

{broken_text}

أصلح صياغة الـ JSON فقط (أقواس ناقصة، فواصل زائدة أو ناقصة، علامات اقتباس غير مغلقة، إلخ) دون تغيير أي بيانات أو قيم أو اختراع بيانات جديدة لم تكن موجودة. أعد فقط كائن JSON صالحًا واحدًا، بدون أي نص إضافي قبله أو بعده."""

    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=_JSON_FIX_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _extract_response_text(message)
    return _try_parse_json(text)


# ---------------------------------------------------------------------------
# Extraction prompts
# ---------------------------------------------------------------------------
def _bank_statement_prompt() -> str:
    categories = ", ".join(_BANK_CATEGORIES)
    return f"""أنت محلل مالي تستخرج بيانات من كشف حساب بنكي، وقد يمتد على عدة صفحات. \
استخرج كل حركة/معاملة مالية ظاهرة في المستند بالكامل عبر جميع الصفحات، دون الاكتفاء بعينة منها مهما كان عدد الحركات كبيرًا.

لكل معاملة أعد:
- date: التاريخ كما يظهر (بصيغة YYYY-MM-DD إن أمكن استنتاجها، وإلا كما هو مكتوب)
- description: وصف قصير جدًا جدًا لتوفير المساحة (كلمتان إلى أربع كلمات كحد أقصى)
- amount: المبلغ كرقم موجب فقط (بدون إشارة سالبة)
- type: "credit" أو "debit"
- category: واحدة فقط من هذه القائمة الثابتة بالضبط: {categories}

أعد الرد بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، وبالضبط بالشكل التالي:
{{"transactions": [{{"date": "...", "description": "...", "amount": 0, "type": "credit", "category": "..."}}]}}"""


def _financing_statement_prompt() -> str:
    return """أنت محلل مالي تستخرج بيانات من كشف قرض أو تمويل، وقد يمتد على عدة صفحات. \
استخرج كل حركة/معاملة ظاهرة في المستند بالكامل عبر جميع الصفحات (دفعات صرف أو أقساط)، دون الاكتفاء بعينة منها مهما كان عددها.

استخرج أيضًا الحقول العامة التالية للقرض:
- principal_amount: المبلغ الأصلي للقرض كرقم
- remaining_balance: الرصيد المتبقي كرقم
- monthly_installment: القسط الشهري كرقم
- interest_rate: نسبة الفائدة السنوية كرقم (نسبة مئوية بدون علامة %)، أو null إن لم تكن مذكورة
- start_date: تاريخ بداية القرض (YYYY-MM-DD إن أمكن)، أو null إن غير واضح
- end_date: تاريخ نهاية/استحقاق القرض (YYYY-MM-DD إن أمكن)، أو null إن غير واضح
- payment_status: حالة السداد كما تظهر في المستند (مثل current أو late أو closed)، أو null إن غير واضحة

لكل معاملة في قائمة transactions أعد:
- date: التاريخ (YYYY-MM-DD إن أمكن)
- description: وصف قصير جدًا (كلمتان إلى أربع كلمات كحد أقصى)
- amount: المبلغ كرقم موجب
- type: "disbursement" أو "installment"

أعد الرد بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، وبالضبط بالشكل التالي:
{"principal_amount": 0, "remaining_balance": 0, "monthly_installment": 0, "interest_rate": null, "start_date": null, "end_date": null, "payment_status": null, "transactions": [{"date": "...", "description": "...", "amount": 0, "type": "installment"}]}"""


def _extract_statement_data(file_block: dict, institution_type: str) -> dict:
    prompt_text = _bank_statement_prompt() if institution_type == "bank" else _financing_statement_prompt()

    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=_STATEMENT_MAX_TOKENS,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt_text}, file_block]}],
    )
    text = _extract_response_text(message)

    data = _try_parse_json(text)
    if data is None:
        logger.warning("Statement extraction JSON malformed on first pass; attempting a repair pass.")
        data = _fix_json_via_claude(text)

    if not isinstance(data, dict):
        raise ValueError("Could not obtain valid JSON from the statement extraction.")

    return data


# ---------------------------------------------------------------------------
# Validation / normalization of the (possibly messy) extracted data
# ---------------------------------------------------------------------------
def _coerce_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _validate_bank_transactions(data: dict) -> list[dict]:
    raw_transactions = data.get("transactions")
    if not isinstance(raw_transactions, list):
        raise ValueError("Missing 'transactions' list in bank statement extraction")

    normalized = []
    for raw in raw_transactions:
        if not isinstance(raw, dict):
            continue
        txn_type = raw.get("type") if raw.get("type") in ("credit", "debit") else "debit"
        category = raw.get("category") if raw.get("category") in _BANK_CATEGORIES else "other"
        normalized.append(
            {
                "date": raw.get("date"),
                "description": str(raw.get("description") or "")[:120],
                "amount": round(abs(_coerce_float(raw.get("amount"))), 2),
                "type": txn_type,
                "category": category,
            }
        )
    return normalized


def _validate_financing_data(data: dict) -> dict:
    raw_transactions = data.get("transactions")
    transactions = []
    if isinstance(raw_transactions, list):
        for raw in raw_transactions:
            if not isinstance(raw, dict):
                continue
            txn_type = raw.get("type") if raw.get("type") in ("disbursement", "installment") else "installment"
            transactions.append(
                {
                    "date": raw.get("date"),
                    "description": str(raw.get("description") or "")[:120],
                    "amount": round(abs(_coerce_float(raw.get("amount"))), 2),
                    "type": txn_type,
                }
            )

    interest_rate = data.get("interest_rate")
    interest_rate = _coerce_float(interest_rate, default=None) if interest_rate is not None else None

    return {
        "principal_amount": round(_coerce_float(data.get("principal_amount")), 2),
        "remaining_balance": round(_coerce_float(data.get("remaining_balance")), 2),
        "monthly_installment": round(_coerce_float(data.get("monthly_installment")), 2),
        "interest_rate": interest_rate,
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "payment_status": data.get("payment_status"),
        "transactions": transactions,
    }


# ---------------------------------------------------------------------------
# Derived, chart-ready fields (computed server-side, never trusted from the
# model's own arithmetic)
# ---------------------------------------------------------------------------
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})")


def _month_key(date_str) -> str:
    if isinstance(date_str, str):
        match = _MONTH_RE.match(date_str)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    return "unknown"


def _compute_bank_derived(transactions: list[dict]) -> dict:
    monthly: dict[str, dict[str, float]] = {}
    category_totals: dict[str, float] = {}
    total_credits = 0.0
    total_debits = 0.0

    for txn in transactions:
        month = _month_key(txn["date"])
        bucket = monthly.setdefault(month, {"credit": 0.0, "debit": 0.0})
        bucket[txn["type"]] += txn["amount"]
        if txn["type"] == "credit":
            total_credits += txn["amount"]
        else:
            total_debits += txn["amount"]
        category_totals[txn["category"]] = category_totals.get(txn["category"], 0.0) + txn["amount"]

    monthly_breakdown = [
        {"month": month, "credit": round(v["credit"], 2), "debit": round(v["debit"], 2)}
        for month, v in sorted(monthly.items())
    ]

    total_category_amount = sum(category_totals.values())
    category_breakdown = [
        {
            "category": category,
            "amount": round(amount, 2),
            "percentage": round((amount / total_category_amount) * 100, 2) if total_category_amount > 0 else 0.0,
        }
        for category, amount in sorted(category_totals.items(), key=lambda kv: -kv[1])
    ]

    return {
        "monthly_breakdown": monthly_breakdown,
        "category_breakdown": category_breakdown,
        "summary": {
            "total_credits": round(total_credits, 2),
            "total_debits": round(total_debits, 2),
            "net": round(total_credits - total_debits, 2),
            "transaction_count": len(transactions),
        },
    }


def _compute_financing_derived(transactions: list[dict]) -> dict:
    monthly: dict[str, dict[str, float]] = {}
    total_disbursed = 0.0
    total_repaid = 0.0

    for txn in transactions:
        month = _month_key(txn["date"])
        bucket = monthly.setdefault(month, {"disbursement": 0.0, "installment": 0.0})
        bucket[txn["type"]] += txn["amount"]
        if txn["type"] == "disbursement":
            total_disbursed += txn["amount"]
        else:
            total_repaid += txn["amount"]

    monthly_breakdown = [
        {"month": month, "disbursement": round(v["disbursement"], 2), "installment": round(v["installment"], 2)}
        for month, v in sorted(monthly.items())
    ]

    total_amount = total_disbursed + total_repaid
    category_breakdown = [
        {
            "category": "disbursement",
            "amount": round(total_disbursed, 2),
            "percentage": round((total_disbursed / total_amount) * 100, 2) if total_amount > 0 else 0.0,
        },
        {
            "category": "installment",
            "amount": round(total_repaid, 2),
            "percentage": round((total_repaid / total_amount) * 100, 2) if total_amount > 0 else 0.0,
        },
    ]

    return {
        "monthly_breakdown": monthly_breakdown,
        "category_breakdown": category_breakdown,
        "summary": {
            "total_disbursed": round(total_disbursed, 2),
            "total_repaid": round(total_repaid, 2),
            "transaction_count": len(transactions),
        },
    }


def _sanitize_institution_key(name: str) -> str:
    cleaned = re.sub(r"[^\w]+", "_", name.strip(), flags=re.UNICODE).strip("_").lower()
    return cleaned or "institution"


@router.post("/analyze-statement")
def analyze_statement(body: AnalyzeStatementRequest, admin: dict = Depends(get_current_admin)):
    if anthropic_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Statement analysis is currently unavailable.",
        )

    downloaded = _download_file(body.file_url)
    if downloaded is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to download the statement file from the provided URL.",
        )

    file_bytes, media_type = downloaded
    file_block = _file_content_block(file_bytes, media_type)

    try:
        raw_data = _extract_statement_data(file_block, body.institution_type)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Statement extraction failed for uid=%s institution=%s: %s",
            body.uid,
            body.institution_name,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to extract structured data from the statement.",
        ) from exc

    if body.institution_type == "bank":
        transactions = _validate_bank_transactions(raw_data)
        derived = _compute_bank_derived(transactions)
        loan_fields = {
            "principalAmount": 0.0,
            "monthlyInstallment": 0.0,
            "remainingBalance": 0.0,
            "interestRate": None,
            "startDate": None,
            "endDate": None,
            "paymentStatus": None,
        }
    else:
        financing_data = _validate_financing_data(raw_data)
        transactions = financing_data["transactions"]
        derived = _compute_financing_derived(transactions)
        loan_fields = {
            "principalAmount": financing_data["principal_amount"],
            "monthlyInstallment": financing_data["monthly_installment"],
            "remainingBalance": financing_data["remaining_balance"],
            "interestRate": financing_data["interest_rate"],
            "startDate": financing_data["start_date"],
            "endDate": financing_data["end_date"],
            "paymentStatus": financing_data["payment_status"],
        }

    institution_key = _sanitize_institution_key(body.institution_name)

    try:
        db = get_firestore_client()
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc

    from firebase_admin import firestore

    statement_record = {
        "institutionName": body.institution_name,
        "statementType": body.institution_type,
        "fileUrl": body.file_url,
        "transactions": transactions,
        "derived": derived,
        "analyzedAt": firestore.SERVER_TIMESTAMP,
        **loan_fields,
    }

    user_doc_ref = db.collection("users").document(body.uid)
    user_doc_ref.set(
        {
            "statements": {institution_key: statement_record},
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    user_doc_ref.collection("statementAuditLog").add(
        {
            "adminUid": admin["uid"],
            "targetUid": body.uid,
            "institutionName": body.institution_name,
            "institutionKey": institution_key,
            "institutionType": body.institution_type,
            "fileUrl": body.file_url,
            "transactionCount": len(transactions),
            "summary": derived["summary"],
            "createdAt": firestore.SERVER_TIMESTAMP,
        }
    )

    return {
        "institution_key": institution_key,
        "institution_name": body.institution_name,
        "institution_type": body.institution_type,
        "principal_amount": loan_fields["principalAmount"],
        "monthly_installment": loan_fields["monthlyInstallment"],
        "remaining_balance": loan_fields["remainingBalance"],
        "interest_rate": loan_fields["interestRate"],
        "start_date": loan_fields["startDate"],
        "end_date": loan_fields["endDate"],
        "payment_status": loan_fields["paymentStatus"],
        "transaction_count": len(transactions),
        "transactions": transactions,
        "derived": derived,
    }


# ---------------------------------------------------------------------------
# Shared helpers for the letter-drafting / risk-note endpoints below
# ---------------------------------------------------------------------------
def _require_anthropic() -> None:
    if anthropic_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI-assisted admin tools are currently unavailable.",
        )


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


def _customer_identity(user_doc: dict) -> tuple[str, str | None]:
    """Best-known customer name + national ID, preferring KYC-verified data."""
    kyc = user_doc.get("kycVerification") or {}
    name = kyc.get("typedFullName") or kyc.get("extractedFullName") or "العميل"
    national_id = kyc.get("extractedNationalId") or kyc.get("typedNationalId")
    return name, national_id


def _draft_letter(prompt: str, max_tokens: int = 768) -> str:
    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_response_text(message)


# ---------------------------------------------------------------------------
# POST /institution-request
# ---------------------------------------------------------------------------
class InstitutionRequestBody(BaseModel):
    uid: str
    institution_name: str
    request_details: str | None = None


@router.post("/institution-request")
def institution_request(body: InstitutionRequestBody, admin: dict = Depends(get_current_admin)):
    _require_anthropic()
    db = _get_db()
    user_doc = _get_user_doc(db, body.uid)
    name, national_id = _customer_identity(user_doc)

    id_line = f" (رقم الهوية الوطنية: {national_id})" if national_id else ""
    details_line = (
        f"\nتفاصيل إضافية مطلوبة: {body.request_details}" if body.request_details else ""
    )

    prompt = f"""اكتب خطابًا رسميًا باللغة العربية الفصحى موجهًا إلى {body.institution_name}، \
يطلب فيه الحصول على كافة تفاصيل حسابات و/أو قروض العميل {name}{id_line} لدى هذه الجهة \
(الرصيد الحالي، الأقساط الشهرية، تاريخ الفتح، حالة السداد، وأي التزامات قائمة).

اذكر بوضوح أن هذا الطلب مُصرَّح به من قبل العميل نفسه، وأنه وافق على مشاركة بياناته المالية \
لدى هذه الجهة مع منصة DebtLens لأغراض التحليل الائتماني ومراجعة أهليته لخدمات التمويل.{details_line}

اجعل الخطاب رسميًا ومهذبًا ومختصرًا، بصيغة خطاب طلب موجه لبنك أو جهة تمويل. \
اترك اسم الجهة المرسِلة [DebtLens] وتاريخ الخطاب [التاريخ] كما هي بين قوسين ليتم تعبئتها لاحقًا. \
لا تخترع أرقام حسابات أو تواريخ أو تفاصيل لم تُعطَ لك."""

    try:
        letter = _draft_letter(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.error("Institution request letter generation failed for uid=%s: %s", body.uid, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to draft the letter right now. Please try again shortly.",
        ) from exc

    return {
        "uid": body.uid,
        "customer_name": name,
        "institution_name": body.institution_name,
        "letter": letter,
    }


# ---------------------------------------------------------------------------
# POST /bank-request
# ---------------------------------------------------------------------------
class BankRequestBody(BaseModel):
    uid: str
    bank_name: str
    bank_accounts: list[str]


def _extract_identity_from_id_photo(file_block: dict) -> dict:
    prompt_text = (
        "استخرج الاسم الكامل ورقم الهوية الوطنية الظاهرين في صورة بطاقة الهوية المرفقة. "
        'أعد الرد بصيغة JSON فقط، بدون أي نص إضافي، بالضبط بالشكل التالي: '
        '{"full_name": "..." أو null إن لم يكن واضحًا, "national_id": "..." أو null إن لم يكن واضحًا}'
    )

    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt_text}, file_block]}],
    )
    text = _extract_response_text(message)

    data = _try_parse_json(text)
    if data is None:
        data = _fix_json_via_claude(text)
    if not isinstance(data, dict):
        raise ValueError("Could not obtain valid JSON from ID photo identity extraction.")

    data.setdefault("full_name", None)
    data.setdefault("national_id", None)
    return data


@router.post("/bank-request")
def bank_request(body: BankRequestBody, admin: dict = Depends(get_current_admin)):
    _require_anthropic()
    db = _get_db()
    user_doc = _get_user_doc(db, body.uid)

    kyc = user_doc.get("kycVerification") or {}
    id_photo_url = kyc.get("idPhotoUrl")
    if not id_photo_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ID photo on file for this user; cannot verify identity for a bank request.",
        )

    if not body.bank_accounts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bank_accounts must be a non-empty list.")

    downloaded = _download_file(id_photo_url)
    if downloaded is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to download the user's ID photo.",
        )
    file_bytes, media_type = downloaded
    file_block = _file_content_block(file_bytes, media_type)

    try:
        identity = _extract_identity_from_id_photo(file_block)
    except Exception as exc:  # noqa: BLE001
        logger.error("ID photo identity extraction failed for uid=%s: %s", body.uid, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to extract identity from the ID photo.",
        ) from exc

    name = identity.get("full_name") or kyc.get("typedFullName") or "العميل"
    national_id = identity.get("national_id") or kyc.get("typedNationalId")
    id_line = f" (رقم الهوية الوطنية: {national_id})" if national_id else ""

    accounts_lines = "\n".join(f"- {account}" for account in body.bank_accounts)

    prompt = f"""اكتب خطابًا رسميًا باللغة العربية الفصحى موجهًا إلى {body.bank_name}، \
يطلب فيه الحصول على كافة التفاصيل المتعلقة بالحسابات التالية العائدة للعميل {name}{id_line}:

{accounts_lines}

اذكر بوضوح أن هذا الطلب مُصرَّح به من قبل العميل نفسه، وأنه وافق على مشاركة بيانات هذه الحسابات \
مع منصة DebtLens لأغراض التحليل الائتماني ومراجعة أهليته لخدمات التمويل.

اجعل الخطاب رسميًا ومهذبًا ومختصرًا، بصيغة خطاب طلب موجه لبنك. \
اترك اسم الجهة المرسِلة [DebtLens] وتاريخ الخطاب [التاريخ] كما هي بين قوسين ليتم تعبئتها لاحقًا. \
لا تخترع أرقام حسابات أو تواريخ أو تفاصيل لم تُعطَ لك."""

    try:
        letter = _draft_letter(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.error("Bank request letter generation failed for uid=%s: %s", body.uid, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to draft the letter right now. Please try again shortly.",
        ) from exc

    return {
        "uid": body.uid,
        "customer_name": name,
        "national_id": national_id,
        "bank_name": body.bank_name,
        "bank_accounts": body.bank_accounts,
        "letter": letter,
    }


# ---------------------------------------------------------------------------
# POST /user-insight
# ---------------------------------------------------------------------------
class UserInsightBody(BaseModel):
    uid: str


_INSIGHT_RECOMMENDATIONS = {"approve", "approve_with_more_docs", "reject"}


def _parse_user_insight_json(text: str) -> dict:
    data = _try_parse_json(text)
    if data is None:
        data = _fix_json_via_claude(text)
    if not isinstance(data, dict):
        raise ValueError("Could not obtain valid JSON from the user insight generation.")

    if data.get("risk_tier") not in _RISK_TIERS_ARABIC_ADMIN:
        raise ValueError("Missing or invalid 'risk_tier' in user insight JSON")
    if not isinstance(data.get("concerns"), list) or not all(isinstance(c, str) for c in data["concerns"]):
        raise ValueError("Missing or invalid 'concerns' in user insight JSON")
    if data.get("recommendation") not in _INSIGHT_RECOMMENDATIONS:
        raise ValueError("Missing or invalid 'recommendation' in user insight JSON")
    if not isinstance(data.get("notes"), str) or not data["notes"].strip():
        raise ValueError("Missing or invalid 'notes' in user insight JSON")

    return data


_RISK_TIERS_ARABIC_ADMIN = {"منخفض", "متوسط", "مرتفع"}


@router.post("/user-insight")
def user_insight(body: UserInsightBody, admin: dict = Depends(get_current_admin)):
    _require_anthropic()

    try:
        profile = get_user_financial_profile(body.uid)
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc

    accounts_lines = (
        "\n".join(
            f"- {i['institution_name']}: رصيد متبقٍ {i['remaining_balance']} دينار، "
            f"قسط شهري {i['monthly_installment']} دينار"
            for i in profile["institution_breakdown"]
        )
        or "لا توجد حسابات/قروض موثقة عبر كشوفات."
    )
    declared_companies = ", ".join(profile["profile"]["declared_financing_companies"]) or "لا يوجد"
    dti = profile["debt_to_income_percentage"]

    prompt = f"""أنت محلل مخاطر داخلي في مؤسسة تمويل، تكتب ملاحظة داخلية موجزة لفريق المراجعة (هذه الملاحظة داخلية وليست موجهة للعميل).

بيانات المستخدم قيد المراجعة:
- الدخل الشهري: {profile['profile']['monthly_income']} دينار (مصدر البيانات: {profile['data_source']})
- الحالة الوظيفية: {profile['profile']['employment_status']}
- يمتلك مشروعًا خاصًا: {"نعم" if profile['profile']['has_own_business'] else "لا"}
- شركات التمويل المصرح بها من العميل: {declared_companies}
- الحسابات/القروض الموثقة عبر الكشوفات:
{accounts_lines}
- نسبة الدين إلى الدخل: {dti if dti is not None else "غير متوفرة"}%
- علامة تكديس القروض (أخذ قروض من عدة جهات): {"نعم" if profile['stacking_flag'] else "لا"}

قيّم مستوى المخاطرة، وحدد أهم النقاط التي يجب على فريق المراجعة التحقق منها، وقدّم توصية.

أعد ردك بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، وبالضبط بالشكل التالي:
{{"risk_tier": "منخفض" | "متوسط" | "مرتفع", "concerns": ["نقطة للتحقق منها 1", "نقطة للتحقق منها 2"], "recommendation": "approve" | "approve_with_more_docs" | "reject", "notes": "ملاحظة داخلية موجزة من سطرين إلى ثلاثة أسطر للفريق"}}"""

    try:
        message = anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_response_text(message)
        insight = _parse_user_insight_json(text)
    except Exception as exc:  # noqa: BLE001
        logger.error("User insight generation failed for uid=%s: %s", body.uid, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate a user insight right now. Please try again shortly.",
        ) from exc

    return {
        "uid": body.uid,
        "data_source": profile["data_source"],
        "debt_to_income_percentage": dti,
        "stacking_flag": profile["stacking_flag"],
        "risk_tier": insight["risk_tier"],
        "concerns": insight["concerns"],
        "recommendation": insight["recommendation"],
        "notes": insight["notes"],
    }


# ---------------------------------------------------------------------------
# POST /portfolio-summary
# ---------------------------------------------------------------------------
class PortfolioSummaryBody(BaseModel):
    uids: list[str]


@router.post("/portfolio-summary")
def portfolio_summary(body: PortfolioSummaryBody, admin: dict = Depends(get_current_admin)):
    if not body.uids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uids must be a non-empty list.")

    _require_anthropic()
    db = _get_db()

    entries = []
    for uid in body.uids:
        try:
            profile = get_user_financial_profile(uid)
        except FirebaseUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to reach the database right now. Please try again shortly.",
            ) from exc

        user_doc = db.collection("users").document(uid).get().to_dict() or {}
        name, _ = _customer_identity(user_doc)

        entries.append(
            {
                "uid": uid,
                "name": name,
                "active_loans": profile["financing_institutions_with_balance"],
                "debt_to_income_percentage": profile["debt_to_income_percentage"],
                "stacking_flag": profile["stacking_flag"],
                "data_source": profile["data_source"],
            }
        )

    lines = "\n".join(
        f"- {e['name']} (uid: {e['uid']}) — عدد جهات التمويل النشطة: {e['active_loans']}، "
        f"نسبة الدين إلى الدخل: {e['debt_to_income_percentage'] if e['debt_to_income_percentage'] is not None else 'غير متوفرة'}%، "
        f"تكديس قروض: {'نعم' if e['stacking_flag'] else 'لا'}، مصدر البيانات: {e['data_source']}"
        for e in entries
    )

    prompt = f"""أنت محلل مخاطر داخلي في مؤسسة تمويل. لديك قائمة بالمستخدمين الذين ينتظرون مراجعة طلباتهم:

{lines}

رتّب هؤلاء المستخدمين حسب أولوية المراجعة، بحيث يكون أصحاب جهات التمويل النشطة المتعددة (تكديس القروض) في المقدمة، \
ثم من لديهم أعلى نسبة دين إلى دخل. اكتب سطرًا واحدًا فقط لكل مستخدم يشرح سبب ترتيبه، مستخدمًا اسمه كما ورد أعلاه، \
على شكل قائمة عربية مرقّمة (1. 2. 3. ...) بالترتيب من الأعلى أولوية إلى الأقل."""

    try:
        ranked_summary = _draft_letter(prompt, max_tokens=1024)
    except Exception as exc:  # noqa: BLE001
        logger.error("Portfolio summary generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate the portfolio summary right now. Please try again shortly.",
        ) from exc

    return {
        "user_count": len(entries),
        "ranked_summary": ranked_summary,
    }

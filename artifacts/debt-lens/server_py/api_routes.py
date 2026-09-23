"""
JSON API endpoints consumed by the DebtLens dashboard frontend.

Every route here requires a valid Firebase ID token (via `get_current_user`)
and calls `user_data.get_user_financial_profile` first to decide whether the
user has real, statement-verified data or should be told to wait.
"""

import json
import logging
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status

import finance
import market_data
from anthropic_client import ANTHROPIC_MODEL, anthropic_client
from firebase_client import FirebaseUnavailableError, get_current_user
from user_data import get_user_financial_profile

logger = logging.getLogger("debtlens")

router = APIRouter(prefix="/api")

AWAITING_VERIFICATION_MESSAGE = (
    "بياناتك المالية لا تزال قيد المراجعة والتحليل من قبل فريقنا. "
    "سنعلمك فور اكتمال التحليل لعرض نتائجك الدقيقة."
)


def _load_profile(uid: str) -> dict:
    """
    Fetch the unified financial profile, translating a Firebase outage into
    a 503 instead of letting the exception propagate as a 500.
    """
    try:
        return get_user_financial_profile(uid)
    except FirebaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach the database right now. Please try again shortly.",
        ) from exc


def _awaiting_verification_response() -> dict:
    return {
        "awaiting_verification": True,
        "message": AWAITING_VERIFICATION_MESSAGE,
    }


def _require_anthropic() -> None:
    if anthropic_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI-assisted features are currently unavailable.",
        )


def _extract_response_text(message) -> str:
    """Extract the concatenated text content from an Anthropic message response."""
    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip()


def _active_institutions(profile: dict) -> list[dict]:
    """Institutions from the breakdown that still carry a remaining balance."""
    return [
        institution
        for institution in profile["institution_breakdown"]
        if institution["has_remaining_balance"]
    ]


def _build_restructuring_context(profile: dict) -> dict | None:
    """
    Build the loan breakdown + restructuring plan for a verified profile.
    Returns None if there's no active debt to restructure.
    """
    active_institutions = _active_institutions(profile)
    total_remaining_debt = sum(i["remaining_balance"] for i in active_institutions)
    current_monthly_payment = sum(i["monthly_installment"] for i in active_institutions)

    if total_remaining_debt <= 0 or current_monthly_payment <= 0:
        return None

    plan = finance.build_restructuring_plan(total_remaining_debt, current_monthly_payment)

    return {
        "institution_breakdown": active_institutions,
        "restructuring_plan": plan,
    }


# ---------------------------------------------------------------------------
# Homepage news ticker headlines
#
# Public endpoint (no auth) with a 5-minute in-memory cache. If Claude's
# call fails or returns something we can't parse as JSON, we keep serving
# whatever is currently cached rather than erroring out -- and if nothing
# has ever been cached yet, we fall back to the static headlines in
# market_data.py so the ticker never has nothing to show.
# ---------------------------------------------------------------------------
_HEADLINES_CACHE_TTL_SECONDS = 5 * 60
_headlines_cache: dict = {"data": None, "expires_at": 0.0}
_headlines_lock = threading.Lock()


def _fallback_headlines() -> dict:
    static_headlines = market_data.get_market_headlines()
    return {
        "headlines": static_headlines,
        "closing_remark": "ينصح الخبراء المقترضين بمراجعة التزاماتهم الشهرية بانتظام قبل أخذ أي تمويل جديد.",
    }


def _parse_headlines_json(text: str) -> dict:
    """
    Parse Claude's response into {"headlines": [3 strings], "closing_remark": str}.
    Strips markdown code fences if present, and falls back to extracting the
    first {...} block if the response has extra surrounding text.
    """
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

    headlines = data.get("headlines")
    closing_remark = data.get("closing_remark")

    if (
        not isinstance(headlines, list)
        or len(headlines) != 3
        or not all(isinstance(h, str) and h.strip() for h in headlines)
        or not isinstance(closing_remark, str)
        or not closing_remark.strip()
    ):
        raise ValueError("Unexpected headlines JSON shape")

    return {"headlines": headlines, "closing_remark": closing_remark}


def _generate_headlines_via_claude() -> dict:
    prompt = f"""أنت محرر أخبار اقتصادية أردني. بناءً على البيانات الحقيقية التالية:

- سعر الفائدة الرئيسي للبنك المركزي الأردني: {market_data.CBJ_POLICY_RATE_PERCENT:.2f}%
- معدل التضخم السنوي: {market_data.INFLATION_RATE_PERCENT:.1f}%
- احتياطيات العملات الأجنبية لدى البنك المركزي: {market_data.FOREX_RESERVES_USD_BILLION:.1f} مليار دولار

اكتب 3 جمل إخبارية قصيرة باللغة العربية الفصحى بأسلوب نشرة أخبار اقتصادية، كل جملة تتناول أحد المؤشرات الثلاثة أعلاه. \
نوّع في الصياغة والأسلوب في كل مرة بحيث لا تبدو الجمل مكررة أو آلية، لكن حافظ على دقة الأرقام كما هي.

أضف أيضًا ملاحظة ختامية عامة واحدة عن استقرار السوق أو نصيحة للمقترضين.

أعد الرد بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، بالشكل التالي بالضبط:
{{"headlines": ["جملة 1", "جملة 2", "جملة 3"], "closing_remark": "الملاحظة الختامية"}}"""

    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _extract_response_text(message)
    return _parse_headlines_json(text)


def _get_headlines() -> dict:
    now = time.time()

    with _headlines_lock:
        if _headlines_cache["data"] is not None and now < _headlines_cache["expires_at"]:
            return _headlines_cache["data"]

    if anthropic_client is None:
        logger.warning("Anthropic client unavailable; serving cached/fallback headlines.")
        return _headlines_cache["data"] or _fallback_headlines()

    try:
        data = _generate_headlines_via_claude()
    except Exception as exc:  # noqa: BLE001 - any failure falls back to cache
        logger.warning("Headline generation failed, serving cached/fallback headlines: %s", exc)
        return _headlines_cache["data"] or _fallback_headlines()

    with _headlines_lock:
        _headlines_cache["data"] = data
        _headlines_cache["expires_at"] = time.time() + _HEADLINES_CACHE_TTL_SECONDS

    return data


@router.get("/headlines")
def headlines():
    """Public endpoint (no auth) powering the homepage scrolling news ticker."""
    return _get_headlines()


@router.get("/analyze")
def analyze(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    risk_metrics = finance.compute_risk_metrics(profile["transactions"])

    return {
        "awaiting_verification": False,
        "transactions": profile["transactions"],
        "risk_metrics": risk_metrics,
    }


@router.get("/restructure")
def restructure(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    context = _build_restructuring_context(profile)
    if context is None:
        return _awaiting_verification_response()

    return {
        "awaiting_verification": False,
        "institution_breakdown": context["institution_breakdown"],
        "restructuring_plan": context["restructuring_plan"],
    }


@router.get("/advice")
def advice(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    risk_metrics = finance.compute_risk_metrics(profile["transactions"])
    context = _build_restructuring_context(profile)
    restructuring_plan = context["restructuring_plan"] if context else None

    _require_anthropic()

    headlines = "\n".join(f"- {h}" for h in market_data.get_market_headlines())
    plan_summary = (
        f"خيارات إعادة الهيكلة المتاحة: {restructuring_plan['options']}"
        if restructuring_plan
        else "لا توجد ديون نشطة تحتاج إعادة هيكلة حاليًا."
    )

    prompt = f"""أنت مستشار مالي أردني تتحدث باللهجة الأردنية العامية بأسلوب ودي وبسيط.

بيانات المستخدم المالية الحقيقية:
- إجمالي الدخل: {risk_metrics['total_income']} دينار
- إجمالي القروض الجديدة: {risk_metrics['total_new_loans']} دينار
- إجمالي الأقساط الشهرية: {risk_metrics['total_repayments']} دينار
- نسبة الدين إلى الدخل: {risk_metrics['debt_to_income_percentage']}%
- علامة تكديس القروض (أخذ قروض من عدة جهات): {"نعم" if risk_metrics['stacking_flag'] else "لا"}

{plan_summary}

مؤشرات السوق الأردني الحالية:
{headlines}

اكتب 4-5 أسطر فقط من النصيحة المالية باللهجة الأردنية العامية، بأسلوب مباشر وعملي ومتعاطف، بناءً على البيانات أعلاه فقط."""

    try:
        message = anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        advice_text = _extract_response_text(message)
    except Exception as exc:  # noqa: BLE001
        logger.error("Anthropic advice generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate advice right now. Please try again shortly.",
        ) from exc

    return {
        "awaiting_verification": False,
        "advice": advice_text,
        "risk_metrics": risk_metrics,
        "restructuring_plan": restructuring_plan,
    }


@router.get("/consolidation-request")
def consolidation_request(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    context = _build_restructuring_context(profile)
    if context is None:
        return _awaiting_verification_response()

    _require_anthropic()

    breakdown_lines = "\n".join(
        f"- {i['institution_name']}: الرصيد المتبقي {i['remaining_balance']} دينار، "
        f"القسط الشهري {i['monthly_installment']} دينار"
        for i in context["institution_breakdown"]
    )

    prompt = f"""اكتب خطابًا رسميًا باللغة العربية الفصحى موجهًا إلى [Bank Name] نيابة عن العميل [Client Name]، \
يطلب فيه دمج (توحيد) القروض التالية في قرض واحد لتسهيل السداد:

{breakdown_lines}

اجعل الخطاب رسميًا ومهذبًا ومختصرًا، بصيغة خطاب طلب موجه لبنك. \
اترك أماكن مثل [Bank Name] و [Client Name] كما هي بين قوسين ليتم تعبئتها لاحقًا. \
لا تخترع أرقام حسابات أو تواريخ؛ استخدم فقط الأرقام المعطاة أعلاه."""

    try:
        message = anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=768,
            messages=[{"role": "user", "content": prompt}],
        )
        letter_text = _extract_response_text(message)
    except Exception as exc:  # noqa: BLE001
        logger.error("Anthropic consolidation letter generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to draft the letter right now. Please try again shortly.",
        ) from exc

    return {
        "awaiting_verification": False,
        "letter": letter_text,
        "institution_breakdown": context["institution_breakdown"],
    }


@router.get("/financial-summary")
def financial_summary(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    active_institutions = _active_institutions(profile)

    return {
        "awaiting_verification": False,
        "has_active_loans": len(active_institutions) > 0,
        "financing_institutions_count": len(active_institutions),
    }

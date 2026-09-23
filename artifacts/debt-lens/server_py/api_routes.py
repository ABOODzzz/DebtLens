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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

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
        "awaitingVerification": True,
        "message": AWAITING_VERIFICATION_MESSAGE,
    }


class AnalyzeInput(BaseModel):
    type: str


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
    """
    Public endpoint (no auth) powering the homepage scrolling news ticker.

    Returns a list of Headline objects ({id, text, source, publishedAt}) per
    the OpenAPI spec -- _get_headlines() returns the richer internal shape
    ({"headlines": [...], "closing_remark": ...}), so it's adapted here.
    """
    data = _get_headlines()
    published_at = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": i + 1,
            "text": text,
            "source": "البنك المركزي الأردني",
            "publishedAt": published_at,
        }
        for i, text in enumerate(data["headlines"])
    ]


@router.post("/analyze")
def analyze(payload: AnalyzeInput, user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    risk_metrics = finance.compute_risk_metrics(profile["transactions"])

    return {
        "awaitingVerification": False,
        "type": payload.type,
        "transactions": profile["transactions"],
        "risk_metrics": risk_metrics,
    }


@router.post("/restructure")
def restructure(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])

    if profile["data_source"] != "verified":
        return _awaiting_verification_response()

    context = _build_restructuring_context(profile)
    if context is None:
        return _awaiting_verification_response()

    return {
        "awaitingVerification": False,
        "institution_breakdown": context["institution_breakdown"],
        "restructuring_plan": context["restructuring_plan"],
    }


@router.post("/advice")
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
        "awaitingVerification": False,
        "advice": advice_text,
        "risk_metrics": risk_metrics,
        "restructuring_plan": restructuring_plan,
    }


@router.post("/consolidation-request")
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
        "awaitingVerification": False,
        "letter": letter_text,
        "institution_breakdown": context["institution_breakdown"],
    }


# ---------------------------------------------------------------------------
# AI loan eligibility assessment
#
# Unlike the other endpoints above, this one never blocks on
# "awaitingVerification" -- a user with only self-reported onboarding data
# (or none at all) still gets an assessment, just based on synthetic demo
# transactions instead of real statement data. The response always says
# which kind of data it was based on.
#
# The 40-45% debt-to-income ceiling is a hard business rule: Claude is asked
# to respect it, but the server never trusts that alone -- the recommended
# installment/total repayment are always recomputed from the amortization
# formula, and the resulting post-loan DTI is checked again before
# eligibility is finalized.
# ---------------------------------------------------------------------------
_LOAN_ASSESSMENT_MAX_TOKENS = 1024
_LOAN_ASSESSMENT_DTI_CEILING_PERCENT = 45.0
_RISK_TIERS_ARABIC = {"منخفض", "متوسط", "مرتفع"}

# When a Digital Guarantor (see guarantor.py) is backing the request, the
# hard debt-to-income ceiling is relaxed slightly -- this is the concrete,
# server-enforced effect of having a guarantor, on top of Claude being asked
# to consider a friendlier rate.
_GUARANTOR_DTI_CEILING_PERCENT = 50.0


def _guarantor_context(profile: dict) -> dict | None:
    """
    If the applicant has an approved Digital Guarantor, re-validate that
    person still qualifies (their situation may have changed since they
    approved) before letting the boost apply. Never trust a stale approval.
    """
    guarantor_uid = profile.get("guarantor_uid")
    if not guarantor_uid:
        return None

    from guarantor import GUARANTOR_BACKED_MAX_AMOUNT, GUARANTOR_MAX_DTI_PERCENT

    try:
        guarantor_profile = get_user_financial_profile(guarantor_uid)
    except FirebaseUnavailableError:
        return None

    if guarantor_profile["data_source"] != "verified":
        return None
    dti = guarantor_profile["debt_to_income_percentage"]
    if guarantor_profile["stacking_flag"] or (dti is not None and dti >= GUARANTOR_MAX_DTI_PERCENT):
        return None

    return {
        "guarantor_dti_percentage": dti or 0.0,
        "max_backed_amount": GUARANTOR_BACKED_MAX_AMOUNT,
    }


def _loan_assessment_data(profile: dict) -> dict:
    """
    Decide what income/obligation figures to feed the assessment: real,
    statement-derived numbers when verified, otherwise synthetic demo
    transactions -- while always keeping the real, self-reported employment
    and business fields since those aren't tied to statement verification.
    """
    if profile["data_source"] == "verified":
        transactions = profile["transactions"]
        is_real_data = True
        financing_institutions_count = profile["financing_institutions_with_balance"]
    else:
        transactions = finance.generate_demo_transactions()
        is_real_data = False
        financing_institutions_count = len(
            profile["profile"]["declared_financing_companies"]
        )

    risk_metrics = finance.compute_risk_metrics(transactions)

    return {
        "is_real_data": is_real_data,
        "monthly_income": risk_metrics["total_income"],
        "current_monthly_obligations": risk_metrics["total_repayments"],
        "debt_to_income_percentage": risk_metrics["debt_to_income_percentage"] or 0.0,
        "financing_institutions_count": financing_institutions_count,
    }


def _parse_loan_assessment_json(text: str) -> dict:
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
        raise ValueError("Loan assessment JSON is not an object")
    if not isinstance(data.get("eligible"), bool):
        raise ValueError("Missing or invalid 'eligible' in loan assessment JSON")
    if not isinstance(data.get("recommendation"), str) or not data["recommendation"].strip():
        raise ValueError("Missing or invalid 'recommendation' in loan assessment JSON")
    if data.get("risk_tier") not in _RISK_TIERS_ARABIC:
        data["risk_tier"] = "مرتفع" if not data.get("eligible") else "متوسط"

    for field in ["recommended_amount", "interest_rate", "term_months", "monthly_installment", "total_repayment"]:
        data.setdefault(field, None)

    credit_score = data.get("credit_score")
    if not isinstance(credit_score, (int, float)) or not (300 <= credit_score <= 850):
        data["credit_score"] = None
    else:
        data["credit_score"] = int(round(credit_score))

    return data


def _fallback_credit_score(assessment_data: dict, eligible: bool) -> int:
    """
    Deterministic fallback used only when Claude doesn't return a usable
    credit_score -- a simple, transparent heuristic on the same 300-850
    scale, driven by the current debt-to-income ratio and eligibility, so
    the UI always has a number to render.
    """
    dti = assessment_data["debt_to_income_percentage"]
    score = 850 - (dti * 4)
    if not eligible:
        score -= 40
    return int(max(300, min(850, round(score))))


# Bands loosely mirror the familiar FICO-style ranges so the number reads as
# a recognizable "credit score" rather than an arbitrary metric.
_CREDIT_SCORE_BANDS = [
    (579, "ضعيف", "#dc2626"),
    (669, "متوسط", "#f59e0b"),
    (739, "جيد", "#eab308"),
    (799, "جيد جدًا", "#84cc16"),
    (850, "ممتاز", "#16a34a"),
]


def _credit_score_band(score: int) -> tuple[str, str]:
    for ceiling, label, color in _CREDIT_SCORE_BANDS:
        if score <= ceiling:
            return label, color
    return _CREDIT_SCORE_BANDS[-1][1], _CREDIT_SCORE_BANDS[-1][2]


def _generate_loan_assessment_via_claude(
    assessment_data: dict,
    business_info: dict,
    employment_status: str,
    has_own_business: bool,
    guarantor_context: dict | None = None,
) -> dict:
    headlines = "\n".join(f"- {h}" for h in market_data.get_market_headlines())
    business_line = (
        f"لدى المستخدم مشروعه الخاص. تفاصيل إضافية: {business_info}"
        if has_own_business
        else "لا يمتلك المستخدم مشروعًا خاصًا."
    )

    if guarantor_context:
        guarantor_line = (
            f"لدى العميل كفيل رقمي موافق ومُوثّق عند DebtLens بنفسه (نسبة الدين إلى الدخل الخاصة بالكفيل: "
            f"{guarantor_context['guarantor_dti_percentage']}%). الكفيل يتحمل مسؤولية سداد القسط حتى سقف "
            f"{guarantor_context['max_backed_amount']} دينار إذا تعثر العميل. لهذا السبب يمكنك تخفيف نسبة الفائدة "
            "قليلاً مقارنة بعميل بدون كفيل، ضمن الحد الآمن لنسبة الدين إلى الدخل المذكور أدناه."
        )
    else:
        guarantor_line = "لا يوجد كفيل رقمي لهذا العميل."

    dti_ceiling = _GUARANTOR_DTI_CEILING_PERCENT if guarantor_context else _LOAN_ASSESSMENT_DTI_CEILING_PERCENT

    prompt = f"""أنت محلل ائتمان في مؤسسة تمويل أردنية، تقيّم أهلية عميل لقرض جديد.

بيانات العميل الحقيقية:
- الدخل الشهري: {assessment_data['monthly_income']} دينار
- إجمالي الالتزامات الشهرية الحالية (أقساط قائمة): {assessment_data['current_monthly_obligations']} دينار
- نسبة الدين إلى الدخل الحالية (قبل أي قرض جديد): {assessment_data['debt_to_income_percentage']}%
- عدد جهات التمويل النشطة حاليًا: {assessment_data['financing_institutions_count']}
- الحالة الوظيفية: {employment_status}
- {business_line}
- {guarantor_line}

مؤشرات السوق الأردني الحالية:
{headlines}

قاعدة صارمة يجب احترامها دائمًا: قسط أي قرض جديد يجب ألا يرفع نسبة الدين الإجمالية إلى الدخل (الالتزامات الحالية + القسط الجديد، مقسومة على الدخل الشهري) فوق ما يقارب {dti_ceiling}%. \
إذا كانت نسبة الدين الحالية قريبة من هذا الحد أو تجاوزته، أو كان الدخل غير كافٍ أو غير مستقر، فالعميل غير مؤهل حاليًا -- في هذه الحالة لا تقترح أي مبلغ إطلاقًا، واشرح بوضوح أن السبب هو تجاوز الحد الآمن، وانصح بسداد جزء من الديون الحالية أولاً بدلاً من اقتراح قرض جديد.

بالإضافة إلى ذلك، احسب "درجة ائتمانية" عامة للعميل (credit_score) على مقياس عالمي مألوف من 300 إلى 850 (كما في أنظمة التصنيف الائتماني المعروفة)، حيث 300 هي الأضعف و850 هي الأفضل. \
هذه الدرجة تعكس الوضع الائتماني العام للعميل (استقرار الدخل، نسبة الدين إلى الدخل، عدد جهات التمويل النشطة، الحالة الوظيفية) وليست مرتبطة فقط بأهليته لهذا القرض تحديدًا -- \
أي أعطِ درجة حتى لو كان العميل غير مؤهل حاليًا لقرض جديد، فهي تقيس صحته الائتمانية العامة لا قرار هذا الطلب فقط.

أعد ردك بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، وبالضبط بالشكل التالي:
{{
  "eligible": true | false,
  "risk_tier": "منخفض" | "متوسط" | "مرتفع",
  "credit_score": رقم صحيح بين 300 و850,
  "recommended_amount": رقم أو null إذا غير مؤهل,
  "interest_rate": رقم (نسبة سنوية مئوية) أو null إذا غير مؤهل,
  "term_months": رقم صحيح بالأشهر أو null إذا غير مؤهل,
  "monthly_installment": رقم أو null إذا غير مؤهل,
  "total_repayment": رقم أو null إذا غير مؤهل,
  "recommendation": "3-4 أسطر باللهجة الأردنية العامية، بأسلوب ودي ومباشر، تشرح القرار وتقدم نصيحة عملية"
}}"""

    message = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=_LOAN_ASSESSMENT_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _extract_response_text(message)
    return _parse_loan_assessment_json(text)


def _enforce_dti_ceiling(verdict: dict, assessment_data: dict, dti_ceiling_percent: float = _LOAN_ASSESSMENT_DTI_CEILING_PERCENT) -> dict:
    """
    Never trust the model's own arithmetic or its self-reported eligibility
    for the one thing that actually matters here: recompute the installment
    and total repayment from the amortization formula, then recheck the
    resulting debt-to-income ratio against the hard ceiling before
    finalizing eligibility. `dti_ceiling_percent` is relaxed when a
    validated Digital Guarantor is backing the request.
    """
    income = assessment_data["monthly_income"]

    if not verdict["eligible"] or income <= 0:
        verdict["eligible"] = False
        verdict["recommended_amount"] = None
        verdict["interest_rate"] = None
        verdict["term_months"] = None
        verdict["monthly_installment"] = None
        verdict["total_repayment"] = None
        return verdict

    try:
        amount = float(verdict["recommended_amount"])
        annual_rate_percent = float(verdict["interest_rate"])
        term_months = int(verdict["term_months"])
        if amount <= 0 or term_months <= 0 or not (0 < annual_rate_percent < 60):
            raise ValueError("out of sane bounds")
    except (TypeError, ValueError):
        # The model said "eligible" but didn't give us usable numbers to
        # verify -- treat as not eligible rather than guessing.
        verdict["eligible"] = False
        verdict["recommended_amount"] = None
        verdict["interest_rate"] = None
        verdict["term_months"] = None
        verdict["monthly_installment"] = None
        verdict["total_repayment"] = None
        return verdict

    monthly_installment = finance.calculate_monthly_payment(amount, annual_rate_percent / 100, term_months)
    projected_dti = (
        (assessment_data["current_monthly_obligations"] + monthly_installment) / income
    ) * 100

    if projected_dti > dti_ceiling_percent:
        verdict["eligible"] = False
        verdict["recommended_amount"] = None
        verdict["interest_rate"] = None
        verdict["term_months"] = None
        verdict["monthly_installment"] = None
        verdict["total_repayment"] = None
        verdict["recommendation"] = (
            "للأسف ما قدرنا نرشحلك مبلغ قرض جديد هلأ، لأنه راح يرفع نسبة التزاماتك الشهرية "
            "فوق الحد الآمن مقارنة بدخلك. الأفضل تركز على تسديد جزء من التزاماتك الحالية أولاً، "
            "وبعدها نقدر نعيد تقييم أهليتك لقرض جديد."
        )
        return verdict

    verdict["recommended_amount"] = round(amount, 2)
    verdict["interest_rate"] = round(annual_rate_percent, 2)
    verdict["term_months"] = term_months
    verdict["monthly_installment"] = monthly_installment
    verdict["total_repayment"] = round(monthly_installment * term_months, 2)
    return verdict


@router.get("/ai-loan-assessment")
def ai_loan_assessment(user: dict = Depends(get_current_user)):
    profile = _load_profile(user["uid"])
    _require_anthropic()

    assessment_data = _loan_assessment_data(profile)
    guarantor_context = _guarantor_context(profile)

    try:
        verdict = _generate_loan_assessment_via_claude(
            assessment_data,
            business_info=profile["profile"]["business_info"],
            employment_status=profile["profile"]["employment_status"],
            has_own_business=profile["profile"]["has_own_business"],
            guarantor_context=guarantor_context,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("AI loan assessment generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate a loan assessment right now. Please try again shortly.",
        ) from exc

    dti_ceiling = _GUARANTOR_DTI_CEILING_PERCENT if guarantor_context else _LOAN_ASSESSMENT_DTI_CEILING_PERCENT
    verdict = _enforce_dti_ceiling(verdict, assessment_data, dti_ceiling_percent=dti_ceiling)

    if verdict["credit_score"] is None:
        verdict["credit_score"] = _fallback_credit_score(assessment_data, verdict["eligible"])
    credit_score_label, credit_score_color = _credit_score_band(verdict["credit_score"])

    return {
        "eligible": verdict["eligible"],
        "riskTier": verdict["risk_tier"],
        "creditScore": verdict["credit_score"],
        "creditScoreLabel": credit_score_label,
        "creditScoreColor": credit_score_color,
        "guarantorBacked": guarantor_context is not None,
        "recommendedAmount": verdict["recommended_amount"],
        "interestRate": verdict["interest_rate"],
        "termMonths": verdict["term_months"],
        "monthlyInstallment": verdict["monthly_installment"],
        "totalRepayment": verdict["total_repayment"],
        "recommendation": verdict["recommendation"],
        "basedOnRealData": assessment_data["is_real_data"],
        "currentDebtToIncomePercentage": assessment_data["debt_to_income_percentage"],
    }


@router.get("/financial-summary")
def financial_summary(user: dict = Depends(get_current_user)):
    """
    Always returns a fully-populated FinancialSummary, whatever the user's
    data_source is. A brand-new account (no admin-uploaded statements yet,
    "self_reported" or "none") simply has no active institutions yet, so the
    debt figures come back as honest zeros instead of a placeholder shape --
    this endpoint's response must satisfy the FinancialSummary schema on
    every call, since the dashboard renders it unconditionally.
    """
    profile = _load_profile(user["uid"])

    active_institutions = _active_institutions(profile)
    total_remaining_debt = sum(i["remaining_balance"] for i in active_institutions)
    total_monthly_debt_payments = sum(i["monthly_installment"] for i in active_institutions)
    monthly_income = profile["profile"]["monthly_income"]
    debt_to_income_ratio = profile["debt_to_income_percentage"] or 0.0

    return {
        "totalMonthlyIncome": round(monthly_income, 2),
        "totalMonthlyDebtPayments": round(total_monthly_debt_payments, 2),
        "totalRemainingDebt": round(total_remaining_debt, 2),
        "activeLoansCount": len(active_institutions),
        "financingInstitutionsCount": profile["financing_institutions_with_balance"],
        "debtToIncomeRatio": round(debt_to_income_ratio, 2),
        "hasActiveLoans": len(active_institutions) > 0,
        "hasMultipleFinancingInstitutions": profile["stacking_flag"],
        "dataSource": profile["data_source"],
    }

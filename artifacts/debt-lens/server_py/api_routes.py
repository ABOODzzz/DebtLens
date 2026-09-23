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


# ---------------------------------------------------------------------------
# AI loan eligibility assessment
#
# Unlike the other endpoints above, this one never blocks on
# "awaiting_verification" -- a user with only self-reported onboarding data
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

    return data


def _generate_loan_assessment_via_claude(assessment_data: dict, business_info: dict, employment_status: str, has_own_business: bool) -> dict:
    headlines = "\n".join(f"- {h}" for h in market_data.get_market_headlines())
    business_line = (
        f"لدى المستخدم مشروعه الخاص. تفاصيل إضافية: {business_info}"
        if has_own_business
        else "لا يمتلك المستخدم مشروعًا خاصًا."
    )

    prompt = f"""أنت محلل ائتمان في مؤسسة تمويل أردنية، تقيّم أهلية عميل لقرض جديد.

بيانات العميل الحقيقية:
- الدخل الشهري: {assessment_data['monthly_income']} دينار
- إجمالي الالتزامات الشهرية الحالية (أقساط قائمة): {assessment_data['current_monthly_obligations']} دينار
- نسبة الدين إلى الدخل الحالية (قبل أي قرض جديد): {assessment_data['debt_to_income_percentage']}%
- عدد جهات التمويل النشطة حاليًا: {assessment_data['financing_institutions_count']}
- الحالة الوظيفية: {employment_status}
- {business_line}

مؤشرات السوق الأردني الحالية:
{headlines}

قاعدة صارمة يجب احترامها دائمًا: قسط أي قرض جديد يجب ألا يرفع نسبة الدين الإجمالية إلى الدخل (الالتزامات الحالية + القسط الجديد، مقسومة على الدخل الشهري) فوق ما يقارب 40-45%. \
إذا كانت نسبة الدين الحالية قريبة من هذا الحد أو تجاوزته، أو كان الدخل غير كافٍ أو غير مستقر، فالعميل غير مؤهل حاليًا -- في هذه الحالة لا تقترح أي مبلغ إطلاقًا، واشرح بوضوح أن السبب هو تجاوز الحد الآمن، وانصح بسداد جزء من الديون الحالية أولاً بدلاً من اقتراح قرض جديد.

أعد ردك بصيغة JSON فقط، بدون أي نص إضافي قبله أو بعده، وبالضبط بالشكل التالي:
{{
  "eligible": true | false,
  "risk_tier": "منخفض" | "متوسط" | "مرتفع",
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


def _enforce_dti_ceiling(verdict: dict, assessment_data: dict) -> dict:
    """
    Never trust the model's own arithmetic or its self-reported eligibility
    for the one thing that actually matters here: recompute the installment
    and total repayment from the amortization formula, then recheck the
    resulting debt-to-income ratio against the hard ceiling before
    finalizing eligibility.
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

    if projected_dti > _LOAN_ASSESSMENT_DTI_CEILING_PERCENT:
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

    try:
        verdict = _generate_loan_assessment_via_claude(
            assessment_data,
            business_info=profile["profile"]["business_info"],
            employment_status=profile["profile"]["employment_status"],
            has_own_business=profile["profile"]["has_own_business"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("AI loan assessment generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate a loan assessment right now. Please try again shortly.",
        ) from exc

    verdict = _enforce_dti_ceiling(verdict, assessment_data)

    return {
        "eligible": verdict["eligible"],
        "risk_tier": verdict["risk_tier"],
        "recommended_amount": verdict["recommended_amount"],
        "interest_rate": verdict["interest_rate"],
        "term_months": verdict["term_months"],
        "monthly_installment": verdict["monthly_installment"],
        "total_repayment": verdict["total_repayment"],
        "recommendation": verdict["recommendation"],
        "based_on_real_data": assessment_data["is_real_data"],
        "current_debt_to_income_percentage": assessment_data["debt_to_income_percentage"],
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

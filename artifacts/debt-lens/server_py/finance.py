"""
Core financial calculation logic for DebtLens.

Plain Python functions only -- no FastAPI routes here. These are the building
blocks that future API endpoints (transaction analysis, restructuring
proposals, eligibility checks) will call.
"""

import math
from typing import Optional, TypedDict


# ---------------------------------------------------------------------------
# Interest rate constants.
#
# The base annual rate offered to consumers is modeled as the central bank's
# policy rate plus a margin lenders add for consumer loans. Both are kept as
# separate named constants so either can be tuned independently (e.g. when
# the Central Bank of Jordan changes its policy rate).
# ---------------------------------------------------------------------------
CENTRAL_BANK_POLICY_RATE = 0.0725  # 7.25% -- illustrative CBJ policy rate
CONSUMER_LOAN_MARGIN = 0.05  # 5.00% -- typical consumer loan margin over policy rate
BASE_ANNUAL_INTEREST_RATE = CENTRAL_BANK_POLICY_RATE + CONSUMER_LOAN_MARGIN  # 12.25%


# ---------------------------------------------------------------------------
# Transaction classification
# ---------------------------------------------------------------------------

# Keyword lists are checked in this order (loan > repayment > income > other)
# since a description like "loan installment payment" should still register
# as a repayment, not a loan disbursement.
_LOAN_KEYWORDS = [
    "new loan disbursed",
    "loan disbursed",
    "loan disbursement",
    "cash advance",
    "advance disbursed",
    "new loan",
    "qard jadeed",
    "قرض جديد",
    "صرف قرض",
    "دفعة تمويل",
]

_REPAYMENT_KEYWORDS = [
    "installment payment",
    "installment",
    "loan repayment",
    "repayment",
    "monthly payment",
    "دفعة قسط",
    "قسط شهري",
    "سداد",
    "تسديد",
]

_INCOME_KEYWORDS = [
    "salary",
    "payroll",
    "wage",
    "wages",
    "monthly salary",
    "راتب",
    "الراتب الشهري",
]


def classify_transaction(description: str) -> str:
    """
    Classify a transaction description into one of:
    "loan", "repayment", "income", or "other".

    Matching is case-insensitive substring matching against curated keyword
    lists, checked in priority order (loan -> repayment -> income -> other)
    so overlapping phrases (e.g. "loan installment payment") resolve to the
    more specific "repayment" category.
    """
    if not description:
        return "other"

    text = description.strip().lower()

    for keyword in _REPAYMENT_KEYWORDS:
        if keyword.lower() in text:
            return "repayment"

    for keyword in _LOAN_KEYWORDS:
        if keyword.lower() in text:
            return "loan"

    for keyword in _INCOME_KEYWORDS:
        if keyword.lower() in text:
            return "income"

    return "other"


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------


class RiskMetrics(TypedDict):
    total_income: float
    total_new_loans: float
    total_repayments: float
    debt_to_income_percentage: Optional[float]
    stacking_flag: bool
    loan_count: int


def compute_risk_metrics(transactions: list[dict]) -> RiskMetrics:
    """
    Compute risk metrics from a list of transactions.

    Each transaction dict is expected to have at least a "description" and
    an "amount" key. If a transaction already carries a "type" key (one of
    "loan"/"repayment"/"income"/"other"), that is trusted; otherwise the
    type is inferred from the description via `classify_transaction`.

    Returns total income, total new loans, total repayments, the
    debt-to-income percentage (total repayments / total income * 100), and
    a "stacking flag" that is true when 2 or more separate loan
    disbursements are present -- a common early warning sign of someone
    juggling multiple lenders at once.
    """
    total_income = 0.0
    total_new_loans = 0.0
    total_repayments = 0.0
    loan_count = 0

    for transaction in transactions:
        amount = float(transaction.get("amount", 0) or 0)
        tx_type = transaction.get("type") or classify_transaction(
            transaction.get("description", "")
        )

        if tx_type == "income":
            total_income += amount
        elif tx_type == "loan":
            total_new_loans += amount
            loan_count += 1
        elif tx_type == "repayment":
            total_repayments += amount

    debt_to_income_percentage = (
        round((total_repayments / total_income) * 100, 2) if total_income > 0 else None
    )

    return {
        "total_income": round(total_income, 2),
        "total_new_loans": round(total_new_loans, 2),
        "total_repayments": round(total_repayments, 2),
        "debt_to_income_percentage": debt_to_income_percentage,
        "stacking_flag": loan_count >= 2,
        "loan_count": loan_count,
    }


# ---------------------------------------------------------------------------
# Synthetic / demo transactions
# ---------------------------------------------------------------------------


def generate_demo_transactions() -> list[dict]:
    """
    Generate a small set of realistic synthetic transactions (JOD amounts)
    for users who haven't uploaded real bank/lending data yet.

    Includes a monthly salary, loan disbursements from two different fake
    Jordanian lending apps (so the stacking flag trips), and their
    corresponding installment payments.
    """
    return [
        {
            "date": "2026-08-01",
            "description": "Monthly salary deposit",
            "amount": 650.00,
        },
        {
            "date": "2026-08-03",
            "description": "New loan disbursed - Dinarak App",
            "amount": 400.00,
        },
        {
            "date": "2026-08-10",
            "description": "New loan disbursed - Sanad Cash",
            "amount": 250.00,
        },
        {
            "date": "2026-08-15",
            "description": "Installment payment - Dinarak App",
            "amount": 85.00,
        },
        {
            "date": "2026-08-20",
            "description": "Installment payment - Sanad Cash",
            "amount": 55.00,
        },
        {
            "date": "2026-09-01",
            "description": "Monthly salary deposit",
            "amount": 650.00,
        },
        {
            "date": "2026-09-15",
            "description": "Installment payment - Dinarak App",
            "amount": 85.00,
        },
        {
            "date": "2026-09-20",
            "description": "Installment payment - Sanad Cash",
            "amount": 55.00,
        },
    ]


# ---------------------------------------------------------------------------
# Amortization calculators
# ---------------------------------------------------------------------------


def calculate_monthly_payment(
    principal: float, annual_rate: float, term_months: int
) -> float:
    """
    Standard amortization formula for a fixed-rate installment loan.

    `annual_rate` is a decimal (e.g. 0.1225 for 12.25%), not a percentage.
    Raises ValueError for a non-positive principal or term.
    """
    if principal <= 0:
        raise ValueError("principal must be positive")
    if term_months <= 0:
        raise ValueError("term_months must be positive")

    monthly_rate = annual_rate / 12

    if monthly_rate == 0:
        return round(principal / term_months, 2)

    payment = (
        principal
        * monthly_rate
        / (1 - (1 + monthly_rate) ** -term_months)
    )
    return round(payment, 2)


def months_to_payoff(
    principal: float, annual_rate: float, payment_amount: float
) -> float:
    """
    Number of months required to pay off `principal` at `annual_rate`
    (decimal, e.g. 0.1225) with a fixed `payment_amount` per month.

    Raises ValueError if the payment doesn't even cover the first month's
    interest, since the loan would never amortize.
    """
    if principal <= 0:
        raise ValueError("principal must be positive")
    if payment_amount <= 0:
        raise ValueError("payment_amount must be positive")

    monthly_rate = annual_rate / 12

    if monthly_rate == 0:
        return round(principal / payment_amount, 2)

    first_month_interest = principal * monthly_rate
    if payment_amount <= first_month_interest:
        raise ValueError(
            "payment_amount does not cover the first month's interest; "
            "this loan would never be paid off"
        )

    months = -math.log(1 - (monthly_rate * principal) / payment_amount) / math.log(
        1 + monthly_rate
    )
    return round(months, 2)


# ---------------------------------------------------------------------------
# Restructuring plan
# ---------------------------------------------------------------------------


def build_restructuring_plan(
    total_remaining_debt: float, current_monthly_payment: float
) -> dict:
    """
    Propose two restructuring options for someone struggling with their
    current monthly payment:

    1. "extend_term": keep paying off the same debt, but stretch the
       current remaining term by 6 months, lowering the monthly payment.
    2. "consolidate": roll everything into a single new 12-month loan.

    Both options use `BASE_ANNUAL_INTEREST_RATE`. Returns the current
    situation plus both options with their recalculated monthly payments
    and the monthly savings versus the current payment.
    """
    if total_remaining_debt <= 0:
        raise ValueError("total_remaining_debt must be positive")
    if current_monthly_payment <= 0:
        raise ValueError("current_monthly_payment must be positive")

    current_term_months = months_to_payoff(
        total_remaining_debt, BASE_ANNUAL_INTEREST_RATE, current_monthly_payment
    )

    extended_term_months = round(current_term_months) + 6
    extended_payment = calculate_monthly_payment(
        total_remaining_debt, BASE_ANNUAL_INTEREST_RATE, extended_term_months
    )

    consolidated_term_months = 12
    consolidated_payment = calculate_monthly_payment(
        total_remaining_debt, BASE_ANNUAL_INTEREST_RATE, consolidated_term_months
    )

    return {
        "total_remaining_debt": round(total_remaining_debt, 2),
        "current_monthly_payment": round(current_monthly_payment, 2),
        "current_term_months": current_term_months,
        "annual_interest_rate": BASE_ANNUAL_INTEREST_RATE,
        "options": [
            {
                "id": "extend_term",
                "label": "Extend term by 6 months",
                "term_months": extended_term_months,
                "monthly_payment": extended_payment,
                "monthly_savings": round(
                    current_monthly_payment - extended_payment, 2
                ),
            },
            {
                "id": "consolidate",
                "label": "Consolidate into a single 12-month loan",
                "term_months": consolidated_term_months,
                "monthly_payment": consolidated_payment,
                "monthly_savings": round(
                    current_monthly_payment - consolidated_payment, 2
                ),
            },
        ],
    }


# ---------------------------------------------------------------------------
# Eligibility assessment
# ---------------------------------------------------------------------------

_FULLY_ELIGIBLE_DTI_CEILING = 35.0  # debt-to-income % below which is very safe
_NOT_READY_DTI_FLOOR = 50.0  # debt-to-income % at/above which is too risky
_FULLY_ELIGIBLE_MAX_REQUEST_MULTIPLE = 8  # requested amount vs monthly income
_GUARANTOR_REQUEST_MULTIPLE = 6  # above this multiple, a guarantor is required


def assess_eligibility(
    employment_status: str,
    social_security_registered: bool,
    monthly_income: float,
    requested_amount: float,
    debt_to_income_ratio: float,
) -> dict:
    """
    Simple rules-based eligibility assessment for a new loan request.

    `employment_status` is one of "employed", "self_employed", or
    "unemployed". `debt_to_income_ratio` is a percentage (e.g. 42.5 for
    42.5%), representing the applicant's existing debt burden before this
    new request.

    Returns a dict with:
    - "verdict": "fully_eligible" | "eligible_with_conditions" | "not_ready"
    - "guarantor_needed": bool
    - "recommended_lender_type": "bank" | "microfinance"
    - "reasons": list[str] explaining the verdict
    """
    reasons: list[str] = []

    if monthly_income <= 0 or requested_amount <= 0:
        raise ValueError("monthly_income and requested_amount must be positive")

    request_multiple = requested_amount / monthly_income

    is_unemployed = employment_status == "unemployed"
    is_high_dti = debt_to_income_ratio >= _NOT_READY_DTI_FLOOR

    if is_unemployed or is_high_dti:
        verdict = "not_ready"
        if is_unemployed:
            reasons.append("Applicant has no verifiable employment income.")
        if is_high_dti:
            reasons.append(
                f"Existing debt-to-income ratio ({debt_to_income_ratio}%) is at or "
                f"above the {_NOT_READY_DTI_FLOOR}% risk threshold."
            )
    elif (
        employment_status in ("employed", "self_employed")
        and social_security_registered
        and debt_to_income_ratio < _FULLY_ELIGIBLE_DTI_CEILING
        and request_multiple <= _FULLY_ELIGIBLE_MAX_REQUEST_MULTIPLE
    ):
        verdict = "fully_eligible"
        reasons.append(
            f"Stable {employment_status.replace('_', ' ')} income, registered with "
            "social security, low existing debt burden, and a reasonable request size."
        )
    else:
        verdict = "eligible_with_conditions"
        if not social_security_registered:
            reasons.append("Not registered with social security.")
        if debt_to_income_ratio >= _FULLY_ELIGIBLE_DTI_CEILING:
            reasons.append(
                f"Debt-to-income ratio ({debt_to_income_ratio}%) exceeds the "
                f"{_FULLY_ELIGIBLE_DTI_CEILING}% threshold for unconditional approval."
            )
        if request_multiple > _FULLY_ELIGIBLE_MAX_REQUEST_MULTIPLE:
            reasons.append(
                f"Requested amount is {request_multiple:.1f}x monthly income."
            )
        if employment_status == "self_employed":
            reasons.append("Self-employed income is harder to verify.")

    guarantor_needed = verdict != "not_ready" and (
        verdict == "eligible_with_conditions"
        or request_multiple > _GUARANTOR_REQUEST_MULTIPLE
    )

    recommended_lender_type = "bank" if verdict == "fully_eligible" else "microfinance"

    return {
        "verdict": verdict,
        "guarantor_needed": guarantor_needed,
        "recommended_lender_type": recommended_lender_type,
        "reasons": reasons,
    }

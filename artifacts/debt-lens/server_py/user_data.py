"""
Aggregates everything DebtLens knows about a single user from Firestore into
one unified financial profile.

This is the backbone function: almost every user-facing endpoint calls
`get_user_financial_profile` first to decide whether to show real,
statement-verified analysis or ask the user to wait for their documents to
be processed.

Firestore schema assumed here (documented since it isn't defined elsewhere
in the codebase yet):

    users/{uid}:
        monthlySalary / monthlyIncome: number       # self-reported income
        employmentType: "permanent" | "temporary" | "unemployed"
        hasOwnBusiness: bool
        businessInfo: { ... }                        # free-form business details
        declaredFinancingCompanies: [str]             # self-reported lender names
        statements: {                                 # admin-uploaded, AI-analyzed
            "<statementId>": {
                "institutionName": str,
                "statementType": "bank" | "loan",
                "principalAmount": number,
                "monthlyInstallment": number,
                "remainingBalance": number,
                "transactions": [
                    { "date": str, "description": str, "amount": number, "type"?: str }
                ]
            }
        }
"""

import logging

from finance import classify_transaction, compute_risk_metrics
from firebase_client import FirebaseUnavailableError, get_firestore_client

logger = logging.getLogger("debtlens")

__all__ = ["FirebaseUnavailableError", "get_user_financial_profile"]


def _normalize_statement_transactions(
    statement_id: str, institution_name: str, raw_transactions: list
) -> list[dict]:
    """
    Tag every transaction in a statement with its source institution and a
    category (loan/repayment/income/other). Trusts an AI-assigned "type"
    already on the transaction when present, and falls back to keyword
    classification otherwise.
    """
    normalized = []
    for raw in raw_transactions or []:
        description = raw.get("description", "")
        category = raw.get("type") or classify_transaction(description)
        normalized.append(
            {
                "statementId": statement_id,
                "institutionName": institution_name,
                "date": raw.get("date"),
                "description": description,
                "amount": float(raw.get("amount", 0) or 0),
                "type": category,
            }
        )
    return normalized


def _empty_profile(uid: str, data_source: str) -> dict:
    return {
        "uid": uid,
        "data_source": data_source,
        "profile": {
            "monthly_income": 0.0,
            "employment_status": "unemployed",
            "has_own_business": False,
            "business_info": {},
            "declared_financing_companies": [],
        },
        "transactions": [],
        "statement_count": 0,
        "financing_institutions_with_balance": 0,
        "total_loan_principal": 0.0,
        "total_monthly_installments": 0.0,
        "debt_to_income_percentage": None,
        "stacking_flag": False,
        "institution_breakdown": [],
    }


def get_user_financial_profile(uid: str) -> dict:
    """
    Build the unified financial profile for one user.

    Reads users/{uid} for self-reported onboarding data (income, employment
    status, business info, declared financing companies) and its
    "statements" map for admin-uploaded, AI-analyzed bank/loan statements.
    Merges every statement's transactions into one list tagged with source
    institution and category, sums total loan principal and total monthly
    installments, counts financing institutions that still carry a
    remaining balance, and computes the debt-to-income ratio and stacking
    flag -- preferring real statement data over self-reported figures
    whenever statements exist.

    Returns a dict whose "data_source" is:
    - "verified": at least one processed statement exists.
    - "self_reported": no statements, but onboarding data was provided.
    - "none": neither exists yet.

    Raises:
        ValueError: if uid is falsy.
        FirebaseUnavailableError: if Firestore can't be reached because
            Firebase Admin isn't configured. Callers should treat this as a
            503 (service unavailable), not a missing-user 404.
    """
    if not uid:
        raise ValueError("uid is required")

    db = get_firestore_client()

    doc_ref = db.collection("users").document(uid)
    snapshot = doc_ref.get()

    if not snapshot.exists:
        return _empty_profile(uid, data_source="none")

    user_doc = snapshot.to_dict() or {}

    # --- Self-reported onboarding data --------------------------------------
    monthly_income = float(user_doc.get("monthlySalary") or user_doc.get("monthlyIncome") or 0)
    employment_status = user_doc.get("employmentType") or "unemployed"
    has_own_business = bool(user_doc.get("hasOwnBusiness", False))
    business_info = user_doc.get("businessInfo") or {}
    declared_financing_companies = user_doc.get("declaredFinancingCompanies") or []

    # --- Admin-uploaded, AI-analyzed statements ------------------------------
    statements_map = user_doc.get("statements") or {}
    if not isinstance(statements_map, dict):
        logger.warning("users/%s.statements is not a map; ignoring it.", uid)
        statements_map = {}

    all_transactions: list[dict] = []
    total_loan_principal = 0.0
    total_monthly_installments = 0.0
    institutions_with_balance = set()
    # Keyed by lowercased institution name so multiple statements from the
    # same lender aggregate into one breakdown entry.
    institution_totals: dict[str, dict] = {}

    for statement_id, statement in statements_map.items():
        if not isinstance(statement, dict):
            continue

        institution_name = statement.get("institutionName") or "Unknown"
        remaining_balance = float(statement.get("remainingBalance", 0) or 0)
        principal_amount = float(statement.get("principalAmount", 0) or 0)
        monthly_installment = float(statement.get("monthlyInstallment", 0) or 0)

        total_loan_principal += principal_amount
        total_monthly_installments += monthly_installment

        institution_key = institution_name.strip().lower()
        bucket = institution_totals.setdefault(
            institution_key,
            {
                "institution_name": institution_name,
                "principal_amount": 0.0,
                "monthly_installment": 0.0,
                "remaining_balance": 0.0,
            },
        )
        bucket["principal_amount"] += principal_amount
        bucket["monthly_installment"] += monthly_installment
        bucket["remaining_balance"] += remaining_balance

        if remaining_balance > 0:
            institutions_with_balance.add(institution_key)

        all_transactions.extend(
            _normalize_statement_transactions(
                statement_id, institution_name, statement.get("transactions")
            )
        )

    institution_breakdown = [
        {
            "institution_name": bucket["institution_name"],
            "principal_amount": round(bucket["principal_amount"], 2),
            "monthly_installment": round(bucket["monthly_installment"], 2),
            "remaining_balance": round(bucket["remaining_balance"], 2),
            "has_remaining_balance": bucket["remaining_balance"] > 0,
        }
        for bucket in institution_totals.values()
    ]

    has_statements = len(statements_map) > 0

    if has_statements:
        data_source = "verified"
        risk_metrics = compute_risk_metrics(all_transactions)
        # Prefer real transaction-derived income; fall back to the
        # self-reported salary if the statements didn't include any income
        # transactions (e.g. loan-only statements).
        effective_income = risk_metrics["total_income"] or monthly_income
        debt_to_income_percentage = (
            round((total_monthly_installments / effective_income) * 100, 2)
            if effective_income > 0
            else None
        )
        stacking_flag = risk_metrics["stacking_flag"] or len(institutions_with_balance) >= 2
    elif monthly_income > 0 or declared_financing_companies:
        data_source = "self_reported"
        debt_to_income_percentage = None
        declared_set = {c.strip().lower() for c in declared_financing_companies if c}
        stacking_flag = len(declared_set) >= 2
    else:
        data_source = "none"
        debt_to_income_percentage = None
        stacking_flag = False

    return {
        "uid": uid,
        "data_source": data_source,
        "profile": {
            "monthly_income": monthly_income,
            "employment_status": employment_status,
            "has_own_business": has_own_business,
            "business_info": business_info,
            "declared_financing_companies": declared_financing_companies,
        },
        "transactions": all_transactions,
        "statement_count": len(statements_map),
        "financing_institutions_with_balance": len(institutions_with_balance),
        "total_loan_principal": round(total_loan_principal, 2),
        "total_monthly_installments": round(total_monthly_installments, 2),
        "debt_to_income_percentage": debt_to_income_percentage,
        "stacking_flag": stacking_flag,
        "institution_breakdown": institution_breakdown,
    }

"""Customer analysis and loan assessment share the stored admin bank extraction."""

import os
import sys
from types import SimpleNamespace

SERVER_PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_PY_DIR not in sys.path:
    sys.path.insert(0, SERVER_PY_DIR)

import api_routes  # noqa: E402
import user_data  # noqa: E402


def _profile(monkeypatch, transactions, declared_income=900):
    document = {
        "monthlyIncome": declared_income,
        "manualObligationsDeclared": True,
        "manualObligations": [{"category": "rent", "label": "Rent", "amount": 100}],
        "statements": {
            "bank": {
                "institutionName": "Customer Bank",
                "statementType": "bank",
                "transactions": transactions,
                "remainingBalance": 0,
                "monthlyInstallment": 0,
            }
        },
    }
    snapshot = SimpleNamespace(exists=True, to_dict=lambda: document)
    db = SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda uid: SimpleNamespace(get=lambda: snapshot))
    )
    monkeypatch.setattr(user_data, "get_firestore_client", lambda: db)
    return user_data.get_user_financial_profile("customer")


def test_admin_bank_transactions_feed_customer_charts_advice_and_eligibility(monkeypatch):
    profile = _profile(monkeypatch, [
        {"date": "2026-01-05", "description": "salary", "amount": 800, "type": "credit", "category": "salary"},
        {"date": "2026-01-06", "description": "transfer", "amount": 3000, "type": "credit", "category": "transfers"},
        {"date": "2026-01-07", "description": "groceries", "amount": 200, "type": "debit", "category": "food"},
        {"date": "2026-02-05", "description": "salary", "amount": 1200, "type": "credit", "category": "salary"},
        {"date": "2026-02-07", "description": "groceries", "amount": 350, "type": "debit", "category": "food"},
    ])
    monkeypatch.setattr(api_routes, "get_user_financial_profile", lambda uid: profile)
    monkeypatch.setattr(api_routes.market_data, "get_market_headlines", lambda: [])
    prompts = []

    def respond(**kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Advice based on the bank statement")])

    monkeypatch.setattr(api_routes, "anthropic_client", SimpleNamespace(messages=SimpleNamespace(create=respond)))
    assert profile["profile"]["monthly_income"] == 1000  # Average salary, not 5000 in total credits.
    assert profile["profile"]["income_source"] == "bank_salary"

    analysis = api_routes.analyze(api_routes.AnalyzeInput(type="full"), user={"uid": "customer"})
    assert analysis["monthlyIncome"] == 1000
    assert analysis["monthlyObligations"] == 100
    assert analysis["bankAnalysis"]["summary"] == {
        "total_credits": 5000, "total_debits": 550, "transaction_count": 5, "net": 4450,
    }
    assert analysis["bankAnalysis"]["monthly_breakdown"] == [
        {"month": "2026-01", "credit": 3800, "debit": 200},
        {"month": "2026-02", "credit": 1200, "debit": 350},
    ]
    assert analysis["bankAnalysis"]["category_breakdown"] == [
        {"category": "transfers", "amount": 3000},
        {"category": "salary", "amount": 2000},
        {"category": "food", "amount": 550},
    ]
    summary = api_routes.financial_summary(user={"uid": "customer"})
    assert summary["totalMonthlyIncome"] == 1000
    assert summary["totalMonthlyDebtPayments"] == analysis["monthlyObligations"]
    api_routes.advice(user={"uid": "customer"})
    assert "5000" in prompts[0] and "1000" in prompts[0]
    assert "التحويلات ليست كلها راتبًا" in prompts[0]

    assessment = api_routes._loan_assessment_data(profile)
    assert assessment["monthly_income"] == analysis["monthlyIncome"]
    assert assessment["current_monthly_obligations"] == analysis["monthlyObligations"]
    assert assessment["bank_analysis"] == analysis["bankAnalysis"]


def test_transfers_without_salary_do_not_become_income(monkeypatch):
    profile = _profile(monkeypatch, [
        {"date": "2026-01-06", "description": "transfer", "amount": 3000, "type": "credit", "category": "transfers"},
    ])
    assert profile["profile"]["monthly_income"] == 900
    assert profile["profile"]["income_source"] == "self_reported"
    assert profile["bank_analysis"]["summary"]["total_credits"] == 3000
    assert api_routes._loan_assessment_data(profile)["monthly_income"] == 900


def test_verified_loan_installments_do_not_double_count_declared_loans(monkeypatch):
    profile = _profile(monkeypatch, [])
    profile["total_monthly_installments"] = 180
    profile["profile"]["manual_obligations"].append({"category": "loans", "amount": 180})
    assert api_routes._analysis_totals(profile) == (900, 280)
    assert api_routes._loan_assessment_data(profile)["current_monthly_obligations"] == 280
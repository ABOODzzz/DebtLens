"""Self-reported income and obligations must reach the summary, analysis and advice."""

import os
import sys
from types import SimpleNamespace

import pytest

SERVER_PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_PY_DIR not in sys.path:
    sys.path.insert(0, SERVER_PY_DIR)

import api_routes  # noqa: E402


@pytest.mark.parametrize("obligations", [0, 350])
def test_declared_finances_feed_summary_analysis_and_advice(monkeypatch, obligations):
    profile = {
        "data_source": "self_reported",
        "profile": {
            "monthly_income": 1200,
            "manual_monthly_obligations": obligations,
            "manual_obligations_declared": True,
            "manual_obligations": (
                [{"category": "rent", "label": "إيجار", "amount": obligations}] if obligations else []
            ),
            "employment_status": "permanent",
        },
        "transactions": [],
        "institution_breakdown": [],
        "financing_institutions_with_balance": 0,
        "total_monthly_installments": 0,
        "debt_to_income_percentage": round(obligations / 1200 * 100, 2),
        "stacking_flag": False,
    }
    monkeypatch.setattr(api_routes, "get_user_financial_profile", lambda uid: profile)
    monkeypatch.setattr(
        api_routes,
        "anthropic_client",
        SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
            content=[SimpleNamespace(type="text", text="نصيحة مبنية على الدخل والالتزامات")]
        ))),
    )
    user = {"uid": "self-reported-example"}

    summary = api_routes.financial_summary(user=user)
    analysis = api_routes.analyze(api_routes.AnalyzeInput(type="full"), user=user)
    advice = api_routes.advice(user=user)

    assert summary["totalMonthlyIncome"] == 1200
    assert summary["totalMonthlyDebtPayments"] == obligations
    assert analysis["awaitingVerification"] is False
    assert analysis["monthlyIncome"] == 1200
    assert analysis["monthlyObligations"] == obligations
    assert analysis["disposableIncome"] == 1200 - obligations
    assert advice["awaitingVerification"] is False
    assert advice["advice"]
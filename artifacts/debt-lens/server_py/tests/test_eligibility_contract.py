"""
Contract test for the /ai-loan-assessment endpoint (frontend hook name:
`useAssessLoanEligibility`).

This endpoint feeds the dashboard's "تقييم أهلية التمويل الإضافي"
(EligibilityDialog, see src/pages/dashboard.tsx). The dialog reads
creditScore, creditScoreLabel, creditScoreColor, eligible, recommendation,
recommendedAmount, and monthlyInstallment straight off the JSON response
with no runtime validation of its own, so a backend change that
renames/drops/nulls one of those fields -- or a mismatch between the HTTP
method the frontend calls and the one the backend accepts -- would
silently break the dialog (or make every request fail) in production.

This test:

1. Exercises /api/ai-loan-assessment with a verified test profile using
   the exact HTTP method the generated frontend client uses (POST), so a
   route/client method mismatch fails here instead of as a silent 405 in
   the browser.
2. Validates the JSON response against the OpenAPI schema in
   lib/api-spec/openapi.yaml (LoanEligibilityResult), so a spec/response
   mismatch fails here instead of in the browser.
3. Asserts every field EligibilityDialog actually reads is present and
   non-empty/non-null, since the OpenAPI schema alone doesn't forbid an
   empty string slipping through, and covers both the eligible and
   not-eligible branches since the dialog renders different fields for
   each.
"""

import copy
import os
import sys

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import RefResolver
from jsonschema.validators import validator_for

SERVER_PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.abspath(os.path.join(SERVER_PY_DIR, "..", "..", ".."))
OPENAPI_PATH = os.path.join(REPO_ROOT, "lib", "api-spec", "openapi.yaml")

if SERVER_PY_DIR not in sys.path:
    sys.path.insert(0, SERVER_PY_DIR)

import api_routes  # noqa: E402
from firebase_client import get_current_user  # noqa: E402
from main import app  # noqa: E402

TEST_UID = "eligibility-contract-test-uid"


def _verified_profile_with_active_loans() -> dict:
    """
    A `get_user_financial_profile`-shaped dict for a customer with
    admin-verified statements, healthy income, and a manageable debt load --
    the scenario the dialog is meant to render a real "eligible" verdict
    for.
    """
    transactions = [
        {"date": "2026-01-05", "description": "راتب شهري", "amount": 1500.0, "type": "income"},
        {"date": "2026-02-05", "description": "راتب شهري", "amount": 1500.0, "type": "income"},
        {"date": "2026-01-10", "description": "قسط تمويل السيارات", "amount": 120.0, "type": "repayment"},
        {"date": "2026-02-10", "description": "قسط تمويل السيارات", "amount": 120.0, "type": "repayment"},
    ]

    institution_breakdown = [
        {
            "institution_name": "بنك الإسكان",
            "principal_amount": 3000.0,
            "monthly_installment": 120.0,
            "remaining_balance": 1800.0,
            "has_remaining_balance": True,
        },
    ]

    return {
        "uid": TEST_UID,
        "data_source": "verified",
        "profile": {
            "monthly_income": 1500.0,
            "employment_status": "permanent",
            "has_own_business": False,
            "business_info": {},
            "declared_financing_companies": [],
        },
        "transactions": transactions,
        "statement_count": 2,
        "financing_institutions_with_balance": 1,
        "total_loan_principal": 3000.0,
        "total_monthly_installments": 120.0,
        "debt_to_income_percentage": round((120.0 / 1500.0) * 100, 2),
        "stacking_flag": False,
        "institution_breakdown": institution_breakdown,
        "guarantor_uid": None,
    }


class FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeAnthropicMessage:
    def __init__(self, text: str):
        self.content = [FakeTextBlock(text)]


class FakeAnthropicMessages:
    def __init__(self, response_json: str):
        self._response_json = response_json

    def create(self, **kwargs):
        return FakeAnthropicMessage(self._response_json)


class FakeAnthropicClient:
    def __init__(self, response_json: str):
        self.messages = FakeAnthropicMessages(response_json)


ELIGIBLE_VERDICT_JSON = """{
  "eligible": true,
  "risk_tier": "منخفض",
  "credit_score": 742,
  "recommended_amount": 1000,
  "interest_rate": 8.5,
  "term_months": 24,
  "monthly_installment": 45.5,
  "total_repayment": 1092,
  "recommendation": "وضعك المالي مستقر ونسبة التزاماتك معقولة، فأنت مؤهل لتمويل إضافي بمبلغ محدود."
}"""

NOT_ELIGIBLE_VERDICT_JSON = """{
  "eligible": false,
  "risk_tier": "مرتفع",
  "credit_score": 560,
  "recommended_amount": null,
  "interest_rate": null,
  "term_months": null,
  "monthly_installment": null,
  "total_repayment": null,
  "recommendation": "للأسف ما قدرنا نرشحلك مبلغ قرض جديد هلأ، نسبة التزاماتك الشهرية مرتفعة مقارنة بدخلك."
}"""


@pytest.fixture()
def openapi_spec() -> dict:
    with open(OPENAPI_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _client_with_verdict(monkeypatch, response_json: str) -> TestClient:
    monkeypatch.setattr(
        api_routes, "get_user_financial_profile", lambda uid: copy.deepcopy(_verified_profile_with_active_loans())
    )
    monkeypatch.setattr(api_routes, "anthropic_client", FakeAnthropicClient(response_json))

    app.dependency_overrides[get_current_user] = lambda: {"uid": TEST_UID}
    return TestClient(app)


def _validate_against_schema(instance: dict, schema_name: str, spec: dict) -> None:
    """Validate `instance` against `#/components/schemas/{schema_name}` in the OpenAPI spec."""
    schema = spec["components"]["schemas"][schema_name]
    resolver = RefResolver.from_schema(spec)
    validator_cls = validator_for(schema)
    validator = validator_cls(schema=schema, resolver=resolver)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = "\n".join(f"  - at {list(e.path)}: {e.message}" for e in errors)
        pytest.fail(f"{schema_name} schema validation failed for response {instance!r}:\n{messages}")


class TestEligibilityEndpoint:
    def teardown_method(self, method):
        app.dependency_overrides.pop(get_current_user, None)

    def test_eligible_verdict_matches_schema_and_dashboard_expectations(self, monkeypatch, openapi_spec):
        client = _client_with_verdict(monkeypatch, ELIGIBLE_VERDICT_JSON)

        # EligibilityDialog's `check.mutate()` issues a POST via the
        # generated `useAssessLoanEligibility` hook -- exercise that exact
        # method rather than whatever the route happens to accept.
        response = client.post("/api/ai-loan-assessment")
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanEligibilityResult", openapi_spec)

        # Fields EligibilityDialog reads unconditionally.
        assert data["eligible"] is True
        assert isinstance(data["creditScore"], int)
        assert 300 <= data["creditScore"] <= 850
        assert isinstance(data["creditScoreLabel"], str) and data["creditScoreLabel"].strip()
        assert isinstance(data["creditScoreColor"], str) and data["creditScoreColor"].strip()
        assert isinstance(data["recommendation"], str) and data["recommendation"].strip()

        # Fields EligibilityDialog only renders when `eligible` is true.
        assert isinstance(data["recommendedAmount"], (int, float)) and data["recommendedAmount"] > 0
        assert isinstance(data["monthlyInstallment"], (int, float)) and data["monthlyInstallment"] > 0

    def test_not_eligible_verdict_matches_schema_and_dashboard_expectations(self, monkeypatch, openapi_spec):
        client = _client_with_verdict(monkeypatch, NOT_ELIGIBLE_VERDICT_JSON)

        response = client.post("/api/ai-loan-assessment")
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanEligibilityResult", openapi_spec)

        # Fields EligibilityDialog reads unconditionally, even when the
        # customer isn't eligible for a new loan.
        assert data["eligible"] is False
        assert isinstance(data["creditScore"], int)
        assert 300 <= data["creditScore"] <= 850
        assert isinstance(data["creditScoreLabel"], str) and data["creditScoreLabel"].strip()
        assert isinstance(data["creditScoreColor"], str) and data["creditScoreColor"].strip()
        assert isinstance(data["recommendation"], str) and data["recommendation"].strip()

        # The recommended-amount/installment cards are gated on `eligible`
        # in the dialog, so the backend is free to send null here.
        assert data["recommendedAmount"] is None
        assert data["monthlyInstallment"] is None

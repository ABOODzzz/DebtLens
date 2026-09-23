"""
Contract tests for the /loan-application endpoints (frontend hook names:
`useSubmitLoanApplication`, `useGetCurrentLoanApplication`).

This is the connected "apply for financing" journey (see dashboard.tsx's
LoanApplicationCard / LoanApplicationDialog): a customer submits an amount
and purpose, the server runs the same AI eligibility assessment used by
/ai-loan-assessment, and persists a LoanApplication row whose status is
one of `submitted` (eligible, no guarantor needed), `awaiting_guarantor`
(their DTI only clears the relaxed guarantor ceiling), or `rejected`
(ineligible even with a guarantor). The frontend reads requested_amount,
purpose, status, requires_guarantor, eligible, recommended_amount,
monthly_installment, and recommendation straight off the response with no
runtime validation of its own, so a field rename/drop here would silently
break the dashboard card.

This test exercises both /loan-application (POST) and /loan-application
(GET) against three DTI scenarios (comfortably eligible, guarantor-band,
over the guarantor ceiling) and validates each response against the
LoanApplication OpenAPI schema.
"""

import copy
import os
import sys
from datetime import datetime, timezone

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

TEST_UID = "loan-application-contract-test-uid"


class FakeLoanApplicationStore:
    """
    Records every persisted application and hands back a database-shaped
    row (incrementing id, real timestamps), so the test can assert the
    endpoint actually persists the application -- not just that it
    fabricates a response shape that happens to match the schema.
    """

    def __init__(self):
        self.inserted: list[dict] = []
        self._next_id = 1
        self._rows: dict[int, dict] = {}

    def insert_loan_application(self, uid, requested_amount, purpose, snapshot):
        row_id = self._next_id
        self._next_id += 1
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": row_id,
            "uid": uid,
            "requested_amount": requested_amount,
            "purpose": purpose,
            "guarantor_relationship_id": None,
            "created_at": now,
            "updated_at": now,
            **snapshot,
        }
        self._rows[row_id] = row
        self.inserted.append(row)
        return row

    def get_latest_loan_application(self, uid):
        matches = [r for r in self._rows.values() if r["uid"] == uid]
        return max(matches, key=lambda r: r["id"]) if matches else None


def _profile_with_dti(monthly_income: float, monthly_repayments: float) -> dict:
    """A verified profile with a chosen current debt-to-income ratio."""
    transactions = [
        {"date": "2026-01-05", "description": "راتب شهري", "amount": monthly_income, "type": "income"},
        {"date": "2026-02-05", "description": "راتب شهري", "amount": monthly_income, "type": "income"},
        {"date": "2026-01-10", "description": "قسط تمويل قائم", "amount": monthly_repayments, "type": "repayment"},
        {"date": "2026-02-10", "description": "قسط تمويل قائم", "amount": monthly_repayments, "type": "repayment"},
    ]
    return {
        "uid": TEST_UID,
        "data_source": "verified",
        "profile": {
            "monthly_income": monthly_income,
            "employment_status": "permanent",
            "has_own_business": False,
            "business_info": {},
            "declared_financing_companies": [],
        },
        "transactions": transactions,
        "statement_count": 2,
        "financing_institutions_with_balance": 1,
        "total_loan_principal": monthly_repayments * 20,
        "total_monthly_installments": monthly_repayments,
        "debt_to_income_percentage": round((monthly_repayments / monthly_income) * 100, 2),
        "stacking_flag": False,
        "institution_breakdown": [],
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


def _verdict_json(eligible: bool) -> str:
    if eligible:
        return """{
  "eligible": true,
  "risk_tier": "منخفض",
  "credit_score": 720,
  "recommended_amount": 500,
  "interest_rate": 9,
  "term_months": 12,
  "monthly_installment": 43.75,
  "total_repayment": 525,
  "recommendation": "وضعك المالي مستقر، تقدر تاخذ هالمبلغ براحة."
}"""
    return """{
  "eligible": false,
  "risk_tier": "مرتفع",
  "credit_score": 540,
  "recommended_amount": null,
  "interest_rate": null,
  "term_months": null,
  "monthly_installment": null,
  "total_repayment": null,
  "recommendation": "التزاماتك الحالية مرتفعة مقارنة بدخلك، ما نقدر نرشحلك مبلغ هلأ."
}"""


@pytest.fixture()
def openapi_spec() -> dict:
    with open(OPENAPI_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def fake_store(monkeypatch):
    fake = FakeLoanApplicationStore()
    monkeypatch.setattr(api_routes.loan_application_store, "insert_loan_application", fake.insert_loan_application)
    monkeypatch.setattr(api_routes.loan_application_store, "get_latest_loan_application", fake.get_latest_loan_application)
    return fake


def _client_for_scenario(monkeypatch, fake_store, monthly_income, monthly_repayments, eligible_json_arg):
    monkeypatch.setattr(
        api_routes,
        "get_user_financial_profile",
        lambda uid: copy.deepcopy(_profile_with_dti(monthly_income, monthly_repayments)),
    )
    monkeypatch.setattr(api_routes, "anthropic_client", FakeAnthropicClient(_verdict_json(eligible_json_arg)))
    monkeypatch.setattr(api_routes, "_guarantor_context", lambda uid: None)

    app.dependency_overrides[get_current_user] = lambda: {"uid": TEST_UID}
    return TestClient(app)


def _validate_against_schema(instance: dict, schema_name: str, spec: dict) -> None:
    schema = spec["components"]["schemas"][schema_name]
    resolver = RefResolver.from_schema(spec)
    validator_cls = validator_for(schema)
    validator = validator_cls(schema=schema, resolver=resolver)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = "\n".join(f"  - at {list(e.path)}: {e.message}" for e in errors)
        pytest.fail(f"{schema_name} schema validation failed for response {instance!r}:\n{messages}")


class TestLoanApplicationEndpoints:
    def teardown_method(self, method):
        app.dependency_overrides.pop(get_current_user, None)

    def test_low_dti_application_is_submitted(self, monkeypatch, openapi_spec, fake_store):
        # DTI = 100/1500 ~= 6.7%, comfortably under the 45% base ceiling.
        client = _client_for_scenario(monkeypatch, fake_store, 1500.0, 100.0, eligible_json_arg=True)

        response = client.post("/api/loan-application", json={"requested_amount": 500, "purpose": "تجديد المنزل"})
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "submitted"
        assert data["requires_guarantor"] is False
        assert data["eligible"] is True
        assert data["requested_amount"] == 500
        assert data["purpose"] == "تجديد المنزل"
        assert data["recommended_amount"] == 500
        assert fake_store.inserted[0]["uid"] == TEST_UID

        # useGetCurrentLoanApplication issues a GET.
        get_response = client.get("/api/loan-application")
        assert get_response.status_code == 200
        get_data = get_response.json()
        _validate_against_schema(get_data, "LoanApplication", openapi_spec)
        assert get_data["id"] == data["id"]

    def test_mid_band_dti_requires_guarantor_instead_of_rejecting(self, monkeypatch, openapi_spec, fake_store):
        # DTI = 700/1500 ~= 46.7%: over the 45% base ceiling but under the
        # 50% guarantor-relaxed ceiling -- should ask for a guarantor rather
        # than reject outright.
        client = _client_for_scenario(monkeypatch, fake_store, 1500.0, 700.0, eligible_json_arg=False)

        response = client.post("/api/loan-application", json={"requested_amount": 500, "purpose": "سيارة"})
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "awaiting_guarantor"
        assert data["requires_guarantor"] is True
        assert data["guarantor_relationship_id"] is None
        assert isinstance(data["recommendation"], str) and data["recommendation"].strip()

    def test_high_dti_application_is_rejected(self, monkeypatch, openapi_spec, fake_store):
        # DTI = 900/1500 = 60%: over even the guarantor-relaxed ceiling.
        client = _client_for_scenario(monkeypatch, fake_store, 1500.0, 900.0, eligible_json_arg=False)

        response = client.post("/api/loan-application", json={"requested_amount": 500, "purpose": "طوارئ"})
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "rejected"
        assert data["requires_guarantor"] is False
        assert data["eligible"] is False
        assert data["recommended_amount"] is None

    def test_get_with_no_application_returns_404(self, monkeypatch, fake_store):
        client = _client_for_scenario(monkeypatch, fake_store, 1500.0, 100.0, eligible_json_arg=True)
        response = client.get("/api/loan-application")
        assert response.status_code == 404

    def test_invalid_amount_is_rejected(self, monkeypatch, fake_store):
        client = _client_for_scenario(monkeypatch, fake_store, 1500.0, 100.0, eligible_json_arg=True)
        response = client.post("/api/loan-application", json={"requested_amount": 0, "purpose": "شيء ما"})
        assert response.status_code == 400

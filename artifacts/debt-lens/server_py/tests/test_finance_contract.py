"""
Contract tests for the /analyze, /restructure, /advice, and
/consolidation-request endpoints.

These endpoints feed the dashboard's "Full Analysis", "Restructure Plan",
"AI Advice", and "Consolidation Request" dialogs (see
src/pages/dashboard.tsx). The dialogs read specific fields off the JSON
response (summary, debtBreakdown, totalRemainingDebt, debtToIncomeRatio,
insights, currentMonthlyBurden, targetMonthlyBurden, months, steps,
advice, generatedAt, id, institutionsIncluded,
estimatedConsolidatedMonthlyPayment) with no runtime validation of their
own, so a backend change that renames/drops/nulls one of those fields
would silently render a blank dialog in production.

This test exercises all four endpoints against a verified test profile
(a customer with active, remaining-balance loans) and:

1. Validates the JSON response against the OpenAPI schema in
   lib/api-spec/openapi.yaml (AnalyzeResult / RestructureResult /
   AdviceResult), so a spec/response mismatch fails here instead of in
   the browser.
2. Asserts every field the dashboard dialogs actually read is present
   and non-empty/non-null, since the OpenAPI schema alone doesn't forbid
   an empty string or an empty list slipping through.
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
import consolidation_store  # noqa: E402
import finance  # noqa: E402
from firebase_client import get_current_user  # noqa: E402
from main import app  # noqa: E402

TEST_UID = "contract-test-uid"


class FakeConsolidationStore:
    """
    Records every persistence call `/consolidation-request` makes and hands
    back a database-shaped row (incrementing id, real timestamp), so the
    test can assert the endpoint actually persists the request -- not just
    that it fabricates a response shape that happens to match the schema.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self._next_id = 1

    def insert_consolidation_request(self, uid, institutions_included, estimated_consolidated_monthly_payment):
        self.calls.append(
            {
                "uid": uid,
                "institutions_included": institutions_included,
                "estimated_consolidated_monthly_payment": estimated_consolidated_monthly_payment,
            }
        )
        row_id = self._next_id
        self._next_id += 1
        return {
            "id": row_id,
            "status": "submitted",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }


def _verified_profile_with_active_loans() -> dict:
    """
    A `get_user_financial_profile`-shaped dict for a customer with
    admin-verified statements and active (remaining-balance) loans --
    the scenario the three dialogs are meant to render real data for.
    """
    transactions = [
        {"date": "2026-01-05", "description": "راتب شهري", "amount": 900.0, "type": "income"},
        {"date": "2026-02-05", "description": "راتب شهري", "amount": 900.0, "type": "income"},
        {"date": "2026-01-10", "description": "قسط تمويل السيارات", "amount": 150.0, "type": "repayment"},
        {"date": "2026-02-10", "description": "قسط تمويل السيارات", "amount": 150.0, "type": "repayment"},
        {"date": "2026-01-15", "description": "قسط تمويل شخصي", "amount": 80.0, "type": "repayment"},
        {"date": "2026-02-15", "description": "قسط تمويل شخصي", "amount": 80.0, "type": "repayment"},
    ]

    institution_breakdown = [
        {
            "institution_name": "بنك الإسكان",
            "principal_amount": 4000.0,
            "monthly_installment": 150.0,
            "remaining_balance": 3200.0,
            "has_remaining_balance": True,
        },
        {
            "institution_name": "شركة التمويل الأردنية",
            "principal_amount": 1500.0,
            "monthly_installment": 80.0,
            "remaining_balance": 900.0,
            "has_remaining_balance": True,
        },
    ]

    return {
        "uid": TEST_UID,
        "data_source": "verified",
        "profile": {
            "monthly_income": 900.0,
            "employment_status": "permanent",
            "has_own_business": False,
            "business_info": {},
            "declared_financing_companies": [],
        },
        "transactions": transactions,
        "statement_count": 2,
        "financing_institutions_with_balance": 2,
        "total_loan_principal": 5500.0,
        "total_monthly_installments": 230.0,
        "debt_to_income_percentage": round((230.0 / 900.0) * 100, 2),
        "stacking_flag": True,
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
    def create(self, **kwargs):
        return FakeAnthropicMessage(
            "لا تشيل هم زايد، بس لازم تراجع التزاماتك الشهرية وتحاول توحّد قروضك "
            "عشان تخفف العبء عن دخلك وتضمن استقرارك المالي بالفترة الجاية."
        )


class FakeAnthropicClient:
    def __init__(self):
        self.messages = FakeAnthropicMessages()


@pytest.fixture()
def openapi_spec() -> dict:
    with open(OPENAPI_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture()
def fake_consolidation_store(monkeypatch):
    fake = FakeConsolidationStore()
    monkeypatch.setattr(api_routes.consolidation_store, "insert_consolidation_request", fake.insert_consolidation_request)
    return fake


@pytest.fixture()
def client(monkeypatch, fake_consolidation_store):
    monkeypatch.setattr(
        api_routes, "get_user_financial_profile", lambda uid: copy.deepcopy(_verified_profile_with_active_loans())
    )
    monkeypatch.setattr(api_routes, "anthropic_client", FakeAnthropicClient())

    app.dependency_overrides[get_current_user] = lambda: {"uid": TEST_UID}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


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


class TestAnalyzeEndpoint:
    def test_full_analysis_matches_schema_and_dashboard_expectations(self, client, openapi_spec):
        response = client.post("/api/analyze", json={"type": "full"})
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "AnalyzeResult", openapi_spec)

        assert data["awaitingVerification"] is False

        # Fields FullAnalysisDialog reads directly off `analysis.data`.
        assert isinstance(data["summary"], str) and data["summary"].strip()
        assert isinstance(data["totalRemainingDebt"], (int, float))
        assert data["totalRemainingDebt"] > 0
        assert isinstance(data["debtToIncomeRatio"], (int, float))

        assert isinstance(data["debtBreakdown"], list) and len(data["debtBreakdown"]) > 0
        for item in data["debtBreakdown"]:
            assert isinstance(item["lenderName"], str) and item["lenderName"].strip()
            assert isinstance(item["remainingAmount"], (int, float))
            assert item["remainingAmount"] > 0

        assert isinstance(data["insights"], list) and len(data["insights"]) > 0
        assert all(isinstance(insight, str) and insight.strip() for insight in data["insights"])


class TestRestructureEndpoint:
    def test_restructure_plan_matches_schema_and_dashboard_expectations(self, client, openapi_spec):
        response = client.post("/api/restructure")
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "RestructureResult", openapi_spec)

        assert data["awaitingVerification"] is False

        # Fields RestructureDialog reads directly off `plan.data`.
        assert isinstance(data["currentMonthlyBurden"], (int, float)) and data["currentMonthlyBurden"] > 0
        assert isinstance(data["targetMonthlyBurden"], (int, float)) and data["targetMonthlyBurden"] > 0
        assert isinstance(data["months"], int) and data["months"] > 0

        assert isinstance(data["steps"], list) and len(data["steps"]) > 0
        for step in data["steps"]:
            assert isinstance(step["lenderName"], str) and step["lenderName"].strip()
            assert isinstance(step["action"], str) and step["action"].strip()
            assert isinstance(step["detail"], str) and step["detail"].strip()


class TestAdviceEndpoint:
    def test_advice_matches_schema_and_dashboard_expectations(self, client, openapi_spec):
        response = client.post("/api/advice")
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "AdviceResult", openapi_spec)

        assert data["awaitingVerification"] is False

        # Fields AiAdviceDialog reads directly off `advice.data`.
        assert isinstance(data["advice"], str) and data["advice"].strip()
        assert isinstance(data["generatedAt"], str) and data["generatedAt"].strip()
        # Must be a real, parseable timestamp (dashboard does `new Date(generatedAt)`).
        datetime.fromisoformat(data["generatedAt"].replace("Z", "+00:00"))


class TestConsolidationRequestEndpoint:
    def test_consolidation_request_matches_schema_and_dashboard_expectations(
        self, client, openapi_spec, fake_consolidation_store
    ):
        response = client.post("/api/consolidation-request")
        assert response.status_code == 201
        data = response.json()

        _validate_against_schema(data, "ConsolidationRequestResult", openapi_spec)

        assert data["awaitingVerification"] is False

        # The request must actually be persisted (real id/status/timestamp
        # from the store), not fabricated in the route handler.
        assert len(fake_consolidation_store.calls) == 1
        persisted_call = fake_consolidation_store.calls[0]
        assert persisted_call["uid"] == TEST_UID
        assert persisted_call["institutions_included"] == data["institutionsIncluded"]
        assert persisted_call["estimated_consolidated_monthly_payment"] == data["estimatedConsolidatedMonthlyPayment"]

        # Fields ConsolidationDialog reads directly off the response.
        assert isinstance(data["id"], int)
        assert data["status"] == "submitted"
        assert isinstance(data["institutionsIncluded"], int) and data["institutionsIncluded"] > 0
        assert isinstance(data["estimatedConsolidatedMonthlyPayment"], (int, float))
        assert data["estimatedConsolidatedMonthlyPayment"] > 0
        assert isinstance(data["createdAt"], str) and data["createdAt"].strip()
        # Must be a real, parseable timestamp.
        datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))


class TestAwaitingVerificationStillWorks:
    """
    Guard the other branch too: when the customer has no verified statements
    yet, the endpoints must return the placeholder shape, not a broken
    attempt at the real one.
    """

    @pytest.fixture()
    def unverified_client(self, monkeypatch):
        monkeypatch.setattr(
            api_routes,
            "get_user_financial_profile",
            lambda uid: {
                "uid": uid,
                "data_source": "none",
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
                "guarantor_uid": None,
            },
        )
        app.dependency_overrides[get_current_user] = lambda: {"uid": TEST_UID}
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_analyze_awaiting_verification_matches_schema(self, unverified_client, openapi_spec):
        response = unverified_client.post("/api/analyze", json={"type": "full"})
        assert response.status_code == 200
        data = response.json()
        _validate_against_schema(data, "AnalyzeResult", openapi_spec)
        assert data["awaitingVerification"] is True
        assert isinstance(data["message"], str) and data["message"].strip()

    def test_restructure_awaiting_verification_matches_schema(self, unverified_client, openapi_spec):
        response = unverified_client.post("/api/restructure")
        assert response.status_code == 200
        data = response.json()
        _validate_against_schema(data, "RestructureResult", openapi_spec)
        assert data["awaitingVerification"] is True

    def test_advice_awaiting_verification_matches_schema(self, unverified_client, openapi_spec):
        response = unverified_client.post("/api/advice")
        assert response.status_code == 200
        data = response.json()
        _validate_against_schema(data, "AdviceResult", openapi_spec)
        assert data["awaitingVerification"] is True

    def test_consolidation_request_awaiting_verification_matches_schema(self, unverified_client, openapi_spec):
        response = unverified_client.post("/api/consolidation-request")
        assert response.status_code == 201
        data = response.json()
        _validate_against_schema(data, "ConsolidationRequestResult", openapi_spec)
        assert data["awaitingVerification"] is True

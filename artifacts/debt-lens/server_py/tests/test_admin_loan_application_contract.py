"""
Contract tests for the admin loan-application review endpoints (frontend
hook names: `useListLoanApplications`, `useSubmitLoanApplicationDecision`).

Once a customer's application reaches `submitted` -- eligible on its own, or
approved-by-guarantor via admin_routes.py's guarantor_decision -- it used to
sit there forever with no way for an admin to make the final disbursement
call. These endpoints let the admin list `submitted` applications (plus
already-decided ones) and approve/reject them, moving the row to a terminal
`approved`/`admin_rejected` status that admin.tsx's LoanApplicationsTab and
dashboard.tsx's LoanApplicationCard both render.

This test validates both endpoints' responses against the OpenAPI schemas in
lib/api-spec/openapi.yaml (AdminLoanApplicationsList, LoanApplication), and
asserts the underlying store only moves a `submitted` row forward -- never a
row that has already been decided.
"""

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

import admin_routes  # noqa: E402
import loan_application_store  # noqa: E402
import notifications  # noqa: E402
from firebase_client import ADMIN_UID, get_current_user  # noqa: E402
from main import app  # noqa: E402

CUSTOMER_UID = "loan-application-admin-test-customer"


def _application_row(app_id: int, status_value: str = "submitted") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": app_id,
        "uid": CUSTOMER_UID,
        "requested_amount": 500.0,
        "purpose": "تجديد المنزل",
        "status": status_value,
        "requires_guarantor": False,
        "guarantor_relationship_id": None,
        "admin_decision_reason": None,
        "eligible": True,
        "risk_tier": "منخفض",
        "credit_score": 720,
        "recommended_amount": 500.0,
        "interest_rate": 9.0,
        "term_months": 12,
        "monthly_installment": 43.75,
        "total_repayment": 525.0,
        "recommendation": "وضعك المالي مستقر.",
        "created_at": now,
        "updated_at": now,
    }


class FakeAdminLoanApplicationStore:
    def __init__(self, rows: dict[int, dict]):
        self._rows = rows

    def list_applications_by_status(self, status_value):
        return [row for row in self._rows.values() if row["status"] == status_value]

    def get_loan_application(self, application_id):
        return self._rows.get(application_id)

    def update_admin_decision(self, application_id, status_value, reason):
        row = self._rows.get(application_id)
        if row is None or row["status"] != "submitted":
            return None
        row = {**row, "status": status_value, "admin_decision_reason": reason}
        self._rows[application_id] = row
        return row


class FakeFirestoreDoc:
    def __init__(self, exists: bool, data: dict | None = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return self._data


class FakeDocRef:
    def __init__(self, data: dict | None):
        self._data = data

    def get(self):
        return FakeFirestoreDoc(self._data is not None, self._data)


class FakeCollection:
    def document(self, doc_id):
        if doc_id == CUSTOMER_UID:
            return FakeDocRef({"kycVerification": {"typedFullName": "أحمد الزعبي"}})
        return FakeDocRef(None)


class FakeDb:
    def collection(self, name):
        return FakeCollection()


@pytest.fixture()
def openapi_spec() -> dict:
    with open(OPENAPI_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_against_schema(instance: dict, schema_name: str, spec: dict) -> None:
    schema = spec["components"]["schemas"][schema_name]
    resolver = RefResolver.from_schema(spec)
    validator_cls = validator_for(schema)
    validator = validator_cls(schema=schema, resolver=resolver)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = "\n".join(f"  - at {list(e.path)}: {e.message}" for e in errors)
        pytest.fail(f"{schema_name} schema validation failed for response {instance!r}:\n{messages}")


class TestAdminLoanApplicationEndpoints:
    def setup_method(self, method):
        self.rows = {1: _application_row(1, "submitted")}
        self.fake_store = FakeAdminLoanApplicationStore(self.rows)

    def teardown_method(self, method):
        app.dependency_overrides.pop(get_current_user, None)

    def _client(self, monkeypatch):
        # admin_routes.py imports loan_application_store *inside* each route
        # function (`import loan_application_store`), so patching attributes
        # on admin_routes itself has no effect -- the patch must land on the
        # real loan_application_store module object those inline imports
        # resolve to. Same reasoning for notifications.notify.
        monkeypatch.setattr(loan_application_store, "list_applications_by_status", self.fake_store.list_applications_by_status)
        monkeypatch.setattr(loan_application_store, "get_loan_application", self.fake_store.get_loan_application)
        monkeypatch.setattr(loan_application_store, "update_admin_decision", self.fake_store.update_admin_decision)
        monkeypatch.setattr(admin_routes, "_get_db", lambda: FakeDb())
        monkeypatch.setattr(notifications, "notify", lambda *args, **kwargs: None)
        app.dependency_overrides[get_current_user] = lambda: {"uid": ADMIN_UID}
        return TestClient(app)

    def test_list_returns_submitted_application_matching_schema(self, monkeypatch, openapi_spec):
        client = self._client(monkeypatch)

        response = client.get("/api/admin/loan-applications")
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "AdminLoanApplicationsList", openapi_spec)
        assert data["awaiting_count"] == 1
        assert data["applications"][0]["id"] == 1
        assert data["applications"][0]["customer_name"] == "أحمد الزعبي"
        assert data["applications"][0]["status"] == "submitted"

    def test_approve_moves_application_to_terminal_state(self, monkeypatch, openapi_spec):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 1, "decision": "approved"},
        )
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "approved"
        assert self.rows[1]["status"] == "approved"

    def test_reject_records_reason_and_terminal_state(self, monkeypatch, openapi_spec):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 1, "decision": "rejected", "reason": "دخل غير مستقر"},
        )
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "admin_rejected"
        assert data["admin_decision_reason"] == "دخل غير مستقر"

    def test_deciding_an_already_decided_application_is_rejected(self, monkeypatch):
        self.rows[1]["status"] = "approved"
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 1, "decision": "approved"},
        )
        assert response.status_code == 400

    def test_deciding_unknown_application_returns_404(self, monkeypatch):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 999, "decision": "approved"},
        )
        assert response.status_code == 404

    def test_non_admin_is_forbidden(self, monkeypatch):
        monkeypatch.setattr(loan_application_store, "list_applications_by_status", self.fake_store.list_applications_by_status)
        app.dependency_overrides[get_current_user] = lambda: {"uid": "not-the-admin"}
        client = TestClient(app)

        response = client.get("/api/admin/loan-applications")
        assert response.status_code == 403

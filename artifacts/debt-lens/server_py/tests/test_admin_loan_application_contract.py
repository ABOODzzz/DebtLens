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
from copy import deepcopy
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


def _application_row(app_id: int, status_value: str = "submitted", updated_at: str | None = None, guarantor_relationship_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": app_id,
        "uid": CUSTOMER_UID,
        "requested_amount": 500.0,
        "purpose": "تجديد المنزل",
        "status": status_value,
        "requires_guarantor": False,
        "guarantor_relationship_id": guarantor_relationship_id,
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
        "updated_at": updated_at or now,
    }


class FakeAdminLoanApplicationStore:
    def __init__(self, rows: dict[int, dict]):
        self._rows = rows
        self.history: dict[int, list[dict]] = {application_id: [] for application_id in rows}

    def list_applications_by_status(self, status_value):
        return [row for row in self._rows.values() if row["status"] == status_value]

    def get_loan_application(self, application_id):
        return self._rows.get(application_id)

    def list_decision_history(self, application_id):
        return self.history.setdefault(application_id, [])

    def update_admin_decision(self, application_id, status_value, reason, admin_uid):
        row = self._rows.get(application_id)
        if row is None or row["status"] != "submitted":
            return None
        row = {**row, "status": status_value, "admin_decision_reason": reason}
        self._rows[application_id] = row
        self.history.setdefault(application_id, []).append(
            {
                "id": len(self.history[application_id]) + 1,
                "application_id": application_id,
                "decision": "rejected" if status_value == "admin_rejected" else status_value,
                "reason": reason,
                "admin_uid": admin_uid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return row

    def revise_admin_decision(self, application_id, new_status, reason, admin_uid):
        row = self._rows.get(application_id)
        if row is None or row["status"] not in ("approved", "admin_rejected"):
            return None
        row = {**row, "status": new_status, "admin_decision_reason": reason}
        self._rows[application_id] = row
        self.history.setdefault(application_id, []).append(
            {
                "id": len(self.history[application_id]) + 1,
                "application_id": application_id,
                "decision": "rejected" if new_status == "admin_rejected" else new_status,
                "reason": reason,
                "admin_uid": admin_uid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return row


class FakeFirestoreDoc:
    def __init__(self, exists: bool, data: dict | None = None, doc_id: str | None = None):
        self.exists = exists
        self._data = data or {}
        self.id = doc_id

    def to_dict(self):
        return self._data


class FakeDocRef:
    def __init__(self, data: dict | None, doc_id: str | None = None):
        self._data = data
        self._doc_id = doc_id

    def get(self):
        return FakeFirestoreDoc(self._data is not None, self._data, self._doc_id)


GUARANTOR_UID = "loan-application-admin-test-guarantor"
RELATIONSHIP_ID = "rel-1"


class FakeCollection:
    def __init__(self, name, relationships: dict[str, dict]):
        self._name = name
        self._relationships = relationships

    def document(self, doc_id):
        if self._name == "users" and doc_id == CUSTOMER_UID:
            return FakeDocRef({"kycVerification": {"typedFullName": "أحمد الزعبي"}})
        if self._name == "guarantorRelationships" and doc_id in self._relationships:
            return FakeDocRef(self._relationships[doc_id])
        return FakeDocRef(None)

class FakeDb:
    def __init__(self, relationships: dict[str, dict] | None = None):
        # Callers that don't care about relationship wiring (e.g. the revise
        # tests) can construct FakeDb() with no args and still exercise the
        # guarantor-notification path via the fixed RELATIONSHIP_ID/GUARANTOR_UID
        # pair below. Callers that need to control validity (approved vs.
        # pending, wrong requester, etc.) pass an explicit dict, including `{}`
        # to simulate no matching relationship.
        self._relationships = (
            {RELATIONSHIP_ID: {"guarantorUid": GUARANTOR_UID}} if relationships is None else relationships
        )

    def collection(self, name):
        return FakeCollection(name, self._relationships)


def _database_application_row(status_value: str) -> dict:
    row = _application_row(1, status_value)
    row["created_at"] = datetime.fromisoformat(row["created_at"])
    row["updated_at"] = datetime.fromisoformat(row["updated_at"])
    return row


class FakeTransactionalDecisionDatabase:
    """Small transactional stand-in for the Postgres store tests.

    The store relies on psycopg2's connection context manager to commit when
    the block succeeds and roll back when an execute raises. Keeping the
    committed state separate from each connection's working copy makes those
    semantics observable without requiring a live database for this contract
    test.
    """

    def __init__(self, application: dict, history: list[dict] | None = None):
        self.applications = {application["id"]: application}
        self.history: list[dict] = deepcopy(history or [])
        self.fail_history_insert = False
        self.commit_count = 0
        self.rollback_count = 0

    def connect(self, *args, **kwargs):
        return FakeTransactionalDecisionConnection(self)


class FakeTransactionalDecisionConnection:
    def __init__(self, database: FakeTransactionalDecisionDatabase):
        self._database = database
        self.applications = deepcopy(database.applications)
        self.history = deepcopy(database.history)
        self._committed = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is None:
            if not self._committed:
                self.commit()
        else:
            self._database.rollback_count += 1
        return False

    def commit(self):
        self._database.applications = deepcopy(self.applications)
        self._database.history = deepcopy(self.history)
        self._database.commit_count += 1
        self._committed = True

    def cursor(self, **kwargs):
        return FakeTransactionalDecisionCursor(self)


class FakeTransactionalDecisionCursor:
    def __init__(self, connection: FakeTransactionalDecisionConnection):
        self._connection = connection
        self._last_row = None

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, query, params):
        normalized_query = " ".join(query.split())

        if normalized_query.startswith("UPDATE loan_applications"):
            status_value, reason, application_id = params
            row = self._connection.applications.get(application_id)
            if "AND status = 'submitted'" in normalized_query:
                matches = row is not None and row["status"] == "submitted"
            else:
                matches = row is not None and row["status"] in ("approved", "admin_rejected")

            if matches:
                row["status"] = status_value
                row["admin_decision_reason"] = reason
                row["updated_at"] = datetime.now(timezone.utc)
                self._last_row = deepcopy(row)
            else:
                self._last_row = None
            return

        if normalized_query.startswith("INSERT INTO loan_application_decision_history"):
            if self._connection._database.fail_history_insert:
                raise RuntimeError("simulated decision history insert failure")

            application_id, decision, reason, admin_uid = params
            self._connection.history.append(
                {
                    "id": len(self._connection.history) + 1,
                    "application_id": application_id,
                    "decision": decision,
                    "reason": reason,
                    "admin_uid": admin_uid,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).replace(
                        second=len(self._connection.history)
                    ),
                }
            )
            return

        raise AssertionError(f"Unexpected SQL in transaction test: {normalized_query}")

    def fetchone(self):
        return deepcopy(self._last_row)


def _approved_relationship(**overrides) -> dict:
    base = {
        "requesterUid": CUSTOMER_UID,
        "requesterName": "أحمد الزعبي",
        "guarantorUid": GUARANTOR_UID,
        "status": "approved",
        "applicationId": 1,
    }
    base.update(overrides)
    return base


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

    def _client(self, monkeypatch, relationships: dict[str, dict] | None = None):
        # admin_routes.py imports loan_application_store *inside* each route
        # function (`import loan_application_store`), so patching attributes
        # on admin_routes itself has no effect -- the patch must land on the
        # real loan_application_store module object those inline imports
        # resolve to. Same reasoning for notifications.notify.
        monkeypatch.setattr(loan_application_store, "list_applications_by_status", self.fake_store.list_applications_by_status)
        monkeypatch.setattr(loan_application_store, "list_decision_history", self.fake_store.list_decision_history)
        monkeypatch.setattr(loan_application_store, "get_loan_application", self.fake_store.get_loan_application)
        monkeypatch.setattr(loan_application_store, "update_admin_decision", self.fake_store.update_admin_decision)
        monkeypatch.setattr(loan_application_store, "revise_admin_decision", self.fake_store.revise_admin_decision)
        monkeypatch.setattr(admin_routes, "_get_db", lambda: FakeDb(relationships))
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
        assert data["applications"][0]["decision_history"] == []

    def test_list_returns_complete_decision_history_for_export(self, monkeypatch, openapi_spec):
        self.rows[1]["status"] = "approved"
        self.fake_store.history[1] = [
            {
                "id": 11,
                "application_id": 1,
                "decision": "approved",
                "reason": None,
                "admin_uid": ADMIN_UID,
                "created_at": "2026-09-22T09:30:00+00:00",
            },
            {
                "id": 12,
                "application_id": 1,
                "decision": "rejected",
                "reason": "دخل غير مستقر",
                "admin_uid": "second-admin",
                "created_at": "2026-09-23T09:30:00+00:00",
            },
        ]
        client = self._client(monkeypatch)

        response = client.get("/api/admin/loan-applications")
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "AdminLoanApplicationsList", openapi_spec)
        assert data["applications"][0]["decision_history"] == self.fake_store.history[1]

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
        assert self.fake_store.history[1][0]["decision"] == "approved"
        assert self.fake_store.history[1][0]["admin_uid"] == ADMIN_UID

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

    def test_decision_notifies_linked_guarantor(self, monkeypatch, openapi_spec):
        self.rows[1]["guarantor_relationship_id"] = RELATIONSHIP_ID
        client = self._client(monkeypatch, relationships={RELATIONSHIP_ID: _approved_relationship()})

        notify_calls = []
        monkeypatch.setattr(
            notifications,
            "notify",
            lambda db, *, uid, notif_type, title, message, related_id=None: notify_calls.append(
                {"uid": uid, "type": notif_type, "title": title, "message": message}
            ),
        )

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 1, "decision": "approved"},
        )
        assert response.status_code == 200

        guarantor_calls = [c for c in notify_calls if c["uid"] == GUARANTOR_UID]
        assert len(guarantor_calls) == 1
        assert guarantor_calls[0]["type"] == "guarantor_backed_application_approved"
        # Message must be unambiguous that this is about a guarantee they gave,
        # not their own application.
        assert "كفلته" in guarantor_calls[0]["message"] or "كفيل" in guarantor_calls[0]["message"]

        applicant_calls = [c for c in notify_calls if c["uid"] == CUSTOMER_UID]
        assert len(applicant_calls) == 1

    def test_decision_with_missing_relationship_skips_guarantor(self, monkeypatch):
        self.rows[1]["guarantor_relationship_id"] = "unknown-relationship"
        client = self._client(monkeypatch, relationships={})

        notify_calls = []
        monkeypatch.setattr(
            notifications,
            "notify",
            lambda db, *, uid, notif_type, title, message, related_id=None: notify_calls.append(uid),
        )

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 1, "decision": "rejected"},
        )
        assert response.status_code == 200
        assert GUARANTOR_UID not in notify_calls

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"status": "pending"}, id="not-yet-approved"),
            pytest.param({"status": "declined"}, id="declined"),
            pytest.param({"requesterUid": "someone-else-uid"}, id="wrong-requester"),
            pytest.param({"applicationId": 999}, id="wrong-application"),
        ],
    )
    def test_decision_skips_guarantor_when_relationship_does_not_validate(self, monkeypatch, overrides):
        self.rows[1]["guarantor_relationship_id"] = RELATIONSHIP_ID
        client = self._client(
            monkeypatch, relationships={RELATIONSHIP_ID: _approved_relationship(**overrides)}
        )

        notify_calls = []
        monkeypatch.setattr(
            notifications,
            "notify",
            lambda db, *, uid, notif_type, title, message, related_id=None: notify_calls.append(uid),
        )

        response = client.post(
            "/api/admin/loan-application-decision",
            json={"application_id": 1, "decision": "approved"},
        )
        assert response.status_code == 200
        assert GUARANTOR_UID not in notify_calls

    def test_non_admin_is_forbidden(self, monkeypatch):
        monkeypatch.setattr(loan_application_store, "list_applications_by_status", self.fake_store.list_applications_by_status)
        app.dependency_overrides[get_current_user] = lambda: {"uid": "not-the-admin"}
        client = TestClient(app)

        response = client.get("/api/admin/loan-applications")
        assert response.status_code == 403


class TestLoanApplicationDecisionStore:
    def _patch_database(self, monkeypatch, database):
        monkeypatch.setattr(loan_application_store, "_database_url", lambda: "transaction-test-db")
        monkeypatch.setattr(loan_application_store.psycopg2, "connect", database.connect)

    @pytest.mark.parametrize(
        ("operation", "initial_status", "next_status"),
        [
            pytest.param("initial", "submitted", "approved", id="initial-decision"),
            pytest.param("revision", "approved", "admin_rejected", id="revised-decision"),
        ],
    )
    def test_audit_insert_failure_rolls_back_application_update(
        self, monkeypatch, operation, initial_status, next_status
    ):
        database = FakeTransactionalDecisionDatabase(_database_application_row(initial_status))
        database.fail_history_insert = True
        self._patch_database(monkeypatch, database)

        with pytest.raises(RuntimeError, match="simulated decision history insert failure"):
            if operation == "initial":
                loan_application_store.update_admin_decision(
                    1, next_status, "decision reason", "admin-uid-1"
                )
            else:
                loan_application_store.revise_admin_decision(
                    1, next_status, "revision reason", "admin-uid-2"
                )

        assert database.applications[1]["status"] == initial_status
        assert database.applications[1]["admin_decision_reason"] is None
        assert database.history == []
        assert database.commit_count == 0
        assert database.rollback_count == 1

    def test_failed_revision_preserves_prior_decision_and_history(self, monkeypatch):
        application = _database_application_row("approved")
        application["admin_decision_reason"] = "initial approval"
        original_history = [
            {
                "id": 1,
                "application_id": 1,
                "decision": "approved",
                "reason": "initial approval",
                "admin_uid": "admin-uid-initial",
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]
        database = FakeTransactionalDecisionDatabase(application, original_history)
        database.fail_history_insert = True
        self._patch_database(monkeypatch, database)

        with pytest.raises(RuntimeError, match="simulated decision history insert failure"):
            loan_application_store.revise_admin_decision(
                1, "admin_rejected", "corrected decision", "admin-uid-revision"
            )

        assert database.applications[1]["status"] == "approved"
        assert database.applications[1]["admin_decision_reason"] == "initial approval"
        assert database.history == original_history
        assert [entry["id"] for entry in database.history] == [1]
        assert database.commit_count == 0
        assert database.rollback_count == 1

    def test_initial_decision_and_revision_append_ordered_admin_history(self, monkeypatch):
        database = FakeTransactionalDecisionDatabase(_database_application_row("submitted"))
        self._patch_database(monkeypatch, database)

        initial = loan_application_store.update_admin_decision(
            1, "approved", "initial approval", "admin-uid-initial"
        )
        revision = loan_application_store.revise_admin_decision(
            1, "admin_rejected", "corrected decision", "admin-uid-revision"
        )

        assert initial["status"] == "approved"
        assert revision["status"] == "admin_rejected"
        assert database.applications[1]["status"] == "admin_rejected"
        assert [entry["id"] for entry in database.history] == [1, 2]
        assert [entry["decision"] for entry in database.history] == ["approved", "rejected"]
        assert [entry["admin_uid"] for entry in database.history] == [
            "admin-uid-initial",
            "admin-uid-revision",
        ]
        assert [entry["reason"] for entry in database.history] == [
            "initial approval",
            "corrected decision",
        ]
        assert database.history[0]["created_at"] < database.history[1]["created_at"]
        assert database.commit_count == 2
        assert database.rollback_count == 0


class TestAdminLoanApplicationRevise:
    """
    Covers /admin/loan-application-revise -- letting an admin walk back a
    recent approved/admin_rejected decision (a misclick, or one made on
    stale information) instead of being stuck with it forever.
    """

    def setup_method(self, method):
        self.rows = {1: _application_row(1, "approved")}
        self.fake_store = FakeAdminLoanApplicationStore(self.rows)
        self.notified: list[dict] = []

    def teardown_method(self, method):
        app.dependency_overrides.pop(get_current_user, None)

    def _client(self, monkeypatch):
        monkeypatch.setattr(loan_application_store, "get_loan_application", self.fake_store.get_loan_application)
        monkeypatch.setattr(loan_application_store, "revise_admin_decision", self.fake_store.revise_admin_decision)
        monkeypatch.setattr(admin_routes, "_get_db", lambda: FakeDb())

        def fake_notify(db, *, uid, notif_type, title, message, related_id=None):
            self.notified.append({"uid": uid, "notif_type": notif_type})

        monkeypatch.setattr(notifications, "notify", fake_notify)
        app.dependency_overrides[get_current_user] = lambda: {"uid": ADMIN_UID}
        return TestClient(app)

    def test_revise_approved_to_rejected_matches_schema_and_notifies_customer(self, monkeypatch, openapi_spec):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "rejected", "reason": "تمت الموافقة بالخطأ على طلب آخر"},
        )
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "admin_rejected"
        assert data["admin_decision_reason"] == "تمت الموافقة بالخطأ على طلب آخر"
        assert self.rows[1]["status"] == "admin_rejected"
        assert self.fake_store.history[1][0]["decision"] == "rejected"
        assert self.fake_store.history[1][0]["admin_uid"] == ADMIN_UID
        assert any(n["uid"] == CUSTOMER_UID and n["notif_type"] == "loan_application_revised" for n in self.notified)

    def test_revise_notifies_backing_guarantor_too(self, monkeypatch):
        self.rows[1] = _application_row(1, "approved", guarantor_relationship_id=RELATIONSHIP_ID)
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "rejected", "reason": "معلومات غير محدّثة"},
        )
        assert response.status_code == 200
        assert any(n["uid"] == GUARANTOR_UID and n["notif_type"] == "loan_application_revised" for n in self.notified)

    def test_revise_back_to_submitted_is_allowed(self, monkeypatch, openapi_spec):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "submitted", "reason": "بحاجة لمراجعة إضافية"},
        )
        assert response.status_code == 200
        data = response.json()

        _validate_against_schema(data, "LoanApplication", openapi_spec)
        assert data["status"] == "submitted"

    def test_revise_still_submitted_application_is_rejected(self, monkeypatch):
        self.rows[1] = _application_row(1, "submitted")
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "approved", "reason": "أي سبب"},
        )
        assert response.status_code == 400

    def test_revise_requires_a_non_empty_reason(self, monkeypatch):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "rejected", "reason": "   "},
        )
        assert response.status_code == 400

    def test_revise_outside_window_is_rejected(self, monkeypatch):
        from datetime import timedelta

        stale_at = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        self.rows[1] = _application_row(1, "approved", updated_at=stale_at)
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "rejected", "reason": "قديم جداً"},
        )
        assert response.status_code == 400

    def test_revise_unknown_application_returns_404(self, monkeypatch):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 999, "new_status": "rejected", "reason": "أي سبب"},
        )
        assert response.status_code == 404

    def test_revise_non_admin_is_forbidden(self, monkeypatch):
        monkeypatch.setattr(loan_application_store, "get_loan_application", self.fake_store.get_loan_application)
        app.dependency_overrides[get_current_user] = lambda: {"uid": "not-the-admin"}
        client = TestClient(app)

        response = client.post(
            "/api/admin/loan-application-revise",
            json={"application_id": 1, "new_status": "rejected", "reason": "أي سبب"},
        )
        assert response.status_code == 403

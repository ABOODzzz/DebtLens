"""Contract tests for revising final digital-guarantor admin decisions."""

import os
import sys
from datetime import datetime, timedelta, timezone

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

REQUESTER_UID = "guarantor-revise-test-requester"
GUARANTOR_UID = "guarantor-revise-test-guarantor"
RELATIONSHIP_ID = "guarantor-revise-rel-1"


class FakeFirestoreDoc:
    def __init__(self, data: dict | None, doc_id: str):
        self.exists = data is not None
        self._data = data or {}
        self.id = doc_id

    def to_dict(self):
        return self._data


class FakeDocRef:
    def __init__(self, data: dict, doc_id: str):
        self.data = data
        self.doc_id = doc_id

    def get(self):
        return FakeFirestoreDoc(self.data, self.doc_id)

    def update(self, values: dict):
        self.data.update(values)


class FakeCollection:
    def __init__(self, relationship: dict):
        self.relationship = relationship

    def document(self, doc_id: str):
        if doc_id != RELATIONSHIP_ID:
            return FakeDocRef({}, doc_id)
        return FakeDocRef(self.relationship, doc_id)


class FakeDb:
    def __init__(self, relationship: dict):
        self.relationship = relationship

    def collection(self, name: str):
        assert name == "guarantorRelationships"
        return FakeCollection(self.relationship)

class ListFakeCollection:
    def __init__(self, snapshots: list[FakeFirestoreDoc], users: dict[str, dict] | None = None):
        self.snapshots = snapshots
        self.users = users or {}

    def stream(self):
        return iter(self.snapshots)

    def where(self, field: str, operator: str, value: str):
        assert operator == "=="
        return ListFakeCollection(
            [snapshot for snapshot in self.snapshots if snapshot.to_dict().get(field) == value],
            self.users,
        )

    def document(self, doc_id: str):
        return FakeDocRef(self.users[doc_id], doc_id)
def _relationship(status_value: str) -> dict:
    return {
        "requesterUid": REQUESTER_UID,
        "guarantorUid": GUARANTOR_UID,
        "status": status_value,
        "applicationId": 42,
        "adminDecisionAt": datetime.now(timezone.utc) - timedelta(days=1),
        "adminDecisionReason": "القرار الأول",
    }

def _history_entries(relationship: dict) -> list[dict]:
    history = relationship.get("adminDecisionHistory", [])
    values = getattr(history, "values", None)
    return list(values if values is not None else history)
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


class TestAdminGuarantorRevise:
    def setup_method(self):
        self.relationship = _relationship("approved")
        self.notified: list[dict] = []
        self.application_updates: list[tuple[str, str]] = []
        self.application_status = "submitted"
        self.application_update_winner: str | None = None

    def teardown_method(self):
        app.dependency_overrides.pop(get_current_user, None)

    def _client(self, monkeypatch):
        monkeypatch.setattr(admin_routes, "_get_db", lambda: FakeDb(self.relationship))
        monkeypatch.setattr(
            loan_application_store,
            "update_status_by_relationship",
            self._update_application_status,
        )
        monkeypatch.setattr(
            notifications,
            "notify",
            lambda db, *, uid, notif_type, title, message, related_id=None: self.notified.append(
                {"uid": uid, "notif_type": notif_type, "message": message}
            ),
        )
        app.dependency_overrides[get_current_user] = lambda: {"uid": ADMIN_UID}
        return TestClient(app)

    def _update_application_status(self, relationship_id: str, new_status: str):
        if self.application_update_winner is not None:
            self.application_status = self.application_update_winner
            return None
        expected_current_status = {
            "submitted": "awaiting_guarantor",
            "awaiting_guarantor": "submitted",
        }[new_status]
        if self.application_status != expected_current_status:
            return None
        self.application_updates.append((relationship_id, new_status))
        self.application_status = new_status
        return {"status": new_status}

    def test_reversing_approval_rejects_and_returns_linked_application_to_guarantor_step(
        self, monkeypatch, openapi_spec
    ):
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-revise",
            json={
                "relationship_id": RELATIONSHIP_ID,
                "new_status": "rejected",
                "reason": "تم اكتشاف معلومات مالية غير محدّثة",
            },
        )

        assert response.status_code == 200
        data = response.json()
        _validate_against_schema(data, "GuarantorDecisionResult", openapi_spec)
        assert data["status"] == "rejected"
        assert self.relationship["status"] == "rejected"
        assert self.relationship["adminDecisionReason"] == "تم اكتشاف معلومات مالية غير محدّثة"
        history = _history_entries(self.relationship)
        assert len(history) == 1
        assert history[0]["previousStatus"] == "approved"
        assert history[0]["newStatus"] == "rejected"
        assert history[0]["reason"] == "تم اكتشاف معلومات مالية غير محدّثة"
        assert history[0]["adminUid"] == ADMIN_UID
        assert isinstance(history[0]["decidedAt"], datetime)
        assert self.application_updates == [(RELATIONSHIP_ID, "awaiting_guarantor")]
        assert {call["uid"] for call in self.notified} == {REQUESTER_UID, GUARANTOR_UID}
        assert all(call["notif_type"] == "guarantor_admin_revised" for call in self.notified)
        assert all("أُعيد طلب التمويل المرتبط" in call["message"] for call in self.notified)

    def test_initial_admin_decision_appends_history_entry(self, monkeypatch, openapi_spec):
        self.relationship = _relationship("awaiting_admin_review")
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-decision",
            json={
                "relationship_id": RELATIONSHIP_ID,
                "decision": "approved",
                "reason": "تم التحقق من أهلية الطرفين",
            },
        )

        assert response.status_code == 200
        data = response.json()
        _validate_against_schema(data, "GuarantorDecisionResult", openapi_spec)
        history = _history_entries(self.relationship)
        assert len(history) == 1
        assert history[0]["previousStatus"] == "awaiting_admin_review"
        assert history[0]["newStatus"] == "approved"
        assert history[0]["reason"] == "تم التحقق من أهلية الطرفين"
        assert history[0]["adminUid"] == ADMIN_UID
        assert isinstance(history[0]["decidedAt"], datetime)

    def test_reversing_rejection_approves_and_moves_linked_application_to_review(self, monkeypatch):
        self.relationship = _relationship("rejected")
        self.application_status = "awaiting_guarantor"
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-revise",
            json={
                "relationship_id": RELATIONSHIP_ID,
                "new_status": "approved",
                "reason": "تمت مراجعة المستندات وتأكيد الأهلية",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert self.application_updates == [(RELATIONSHIP_ID, "submitted")]
        assert {call["uid"] for call in self.notified} == {REQUESTER_UID, GUARANTOR_UID}
        assert all("تحديث حالة طلب التمويل المرتبط" in call["message"] for call in self.notified)

    def test_revising_guarantor_cannot_downgrade_finalized_application(self, monkeypatch):
        self.application_status = "approved"
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-revise",
            json={
                "relationship_id": RELATIONSHIP_ID,
                "new_status": "rejected",
                "reason": "تم اكتشاف معلومات مالية غير محدّثة",
            },
        )

        assert response.status_code == 200
        assert self.application_updates == []
        assert self.application_status == "approved"
        assert all("حُميت النتيجة النهائية" in call["message"] for call in self.notified)

    def test_concurrent_application_decision_wins_over_guarantor_revision(self, monkeypatch):
        self.application_update_winner = "admin_rejected"
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-revise",
            json={
                "relationship_id": RELATIONSHIP_ID,
                "new_status": "rejected",
                "reason": "تم اكتشاف معلومات مالية غير محدّثة",
            },
        )

        assert response.status_code == 200
        assert self.application_updates == []
        assert self.application_status == "admin_rejected"
        assert all("سبقت عملية أخرى هذا التعديل" in call["message"] for call in self.notified)

    @pytest.mark.parametrize(
        ("status_value", "payload", "expected_detail"),
        [
            ("awaiting_admin_review", {"new_status": "approved", "reason": "سبب"}, "hasn't received a final decision"),
            ("approved", {"new_status": "rejected", "reason": "   "}, "reason is required"),
        ],
    )
    def test_revision_requires_final_decision_and_reason(
        self, monkeypatch, status_value, payload, expected_detail
    ):
        self.relationship = _relationship(status_value)
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-revise",
            json={"relationship_id": RELATIONSHIP_ID, **payload},
        )

        assert response.status_code == 400
        assert expected_detail in response.json()["detail"]

    def test_revision_outside_window_is_rejected(self, monkeypatch):
        self.relationship = _relationship("approved")
        self.relationship["adminDecisionAt"] = datetime.now(timezone.utc) - timedelta(days=15)
        client = self._client(monkeypatch)

        response = client.post(
            "/api/admin/guarantor-revise",
            json={
                "relationship_id": RELATIONSHIP_ID,
                "new_status": "rejected",
                "reason": "قرار قديم",
            },
        )

        assert response.status_code == 400
        assert "can no longer be revised" in response.json()["detail"]

def test_admin_guarantor_request_response_includes_complete_decision_history(monkeypatch, openapi_spec):
    first_decision_at = datetime.now(timezone.utc) - timedelta(days=2)
    second_decision_at = datetime.now(timezone.utc) - timedelta(days=1)
    relationship = {
        "requesterUid": REQUESTER_UID,
        "guarantorUid": GUARANTOR_UID,
        "status": "approved",
        "maxAmount": 500.0,
        "requestedAt": first_decision_at - timedelta(days=1),
        "respondedAt": first_decision_at - timedelta(hours=1),
        "adminDecisionHistory": [
            {
                "decidedAt": first_decision_at,
                "previousStatus": "awaiting_admin_review",
                "newStatus": "rejected",
                "reason": "البيانات تحتاج مراجعة",
                "adminUid": ADMIN_UID,
            },
            {
                "decidedAt": second_decision_at,
                "previousStatus": "rejected",
                "newStatus": "approved",
                "reason": "تم استكمال التحقق",
                "adminUid": ADMIN_UID,
            },
        ],
    }
    users = {
        REQUESTER_UID: {"kycVerification": {"typedFullName": "مقدم الطلب", "typedNationalId": "1"}},
        GUARANTOR_UID: {"kycVerification": {"typedFullName": "الكفيل", "typedNationalId": "2"}},
    }

    monkeypatch.setattr(admin_routes, "_get_db", lambda: ListFakeDb(relationship, users))
    monkeypatch.setattr(
        admin_routes,
        "get_user_financial_profile",
        lambda uid: {
            "debt_to_income_percentage": 20.0,
            "stacking_flag": False,
        },
    )

    data = admin_routes.list_guarantor_requests({"uid": ADMIN_UID})

    _validate_against_schema(data, "GuarantorRequestsList", openapi_spec)
    assert data["requests"][0]["decision_history"] == [
        {
            "timestamp": first_decision_at.isoformat(),
            "previous_status": "awaiting_admin_review",
            "new_status": "rejected",
            "reason": "البيانات تحتاج مراجعة",
            "admin_uid": ADMIN_UID,
        },
        {
            "timestamp": second_decision_at.isoformat(),
            "previous_status": "rejected",
            "new_status": "approved",
            "reason": "تم استكمال التحقق",
            "admin_uid": ADMIN_UID,
        },
    ]

class ListFakeDb:
    def __init__(self, relationship: dict, users: dict[str, dict]):
        self.relationships = [FakeFirestoreDoc(relationship, RELATIONSHIP_ID)]
        self.users = users

    def collection(self, name: str):
        if name == "guarantorRelationships":
            return ListFakeCollection(self.relationships, self.users)
        if name == "users":
            return ListFakeCollection(
                [FakeFirestoreDoc(user, uid) for uid, user in self.users.items()],
                self.users,
            )
        raise AssertionError(f"Unexpected collection: {name}")

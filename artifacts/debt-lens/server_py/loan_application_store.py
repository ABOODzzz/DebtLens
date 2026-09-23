"""
Persistence for end-to-end loan/financing applications.

Applications are recorded in the shared `loan_applications` Postgres table
(schema owned by `lib/db/src/schema/loanApplications.ts`), the same store
used for consolidation requests. Each row is a durable record of one
application walking through the connected journey: submit -> AI eligibility
snapshot -> (optional) digital guarantor -> admin review, mirroring the
`guarantorRelationships` Firestore collection it links to via
`guarantor_relationship_id` (see guarantor.py) for the guarantor step.
"""

import logging
import os

import psycopg2
import psycopg2.extras

logger = logging.getLogger("debtlens")


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set. Did you forget to provision a database?")
    return url


def _row_to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "uid": row["uid"],
        "requested_amount": float(row["requested_amount"]),
        "purpose": row["purpose"],
        "status": row["status"],
        "requires_guarantor": row["requires_guarantor"],
        "guarantor_relationship_id": row["guarantor_relationship_id"],
        "admin_decision_reason": row["admin_decision_reason"],
        "eligible": row["eligible"],
        "risk_tier": row["risk_tier"],
        "credit_score": row["credit_score"],
        "recommended_amount": float(row["recommended_amount"]) if row["recommended_amount"] is not None else None,
        "interest_rate": float(row["interest_rate"]) if row["interest_rate"] is not None else None,
        "term_months": row["term_months"],
        "monthly_installment": float(row["monthly_installment"]) if row["monthly_installment"] is not None else None,
        "total_repayment": float(row["total_repayment"]) if row["total_repayment"] is not None else None,
        "recommendation": row["recommendation"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def insert_loan_application(uid: str, requested_amount: float, purpose: str, snapshot: dict) -> dict:
    """
    Insert a new loan application row from an assessment snapshot (see
    api_routes.py's `_submit_loan_application`) and return the full
    persisted record.
    """
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO loan_applications
                    (uid, requested_amount, purpose, status, requires_guarantor,
                     eligible, risk_tier, credit_score, recommended_amount,
                     interest_rate, term_months, monthly_installment,
                     total_repayment, recommendation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uid,
                    requested_amount,
                    purpose,
                    snapshot["status"],
                    snapshot["requires_guarantor"],
                    snapshot["eligible"],
                    snapshot["risk_tier"],
                    snapshot["credit_score"],
                    snapshot["recommended_amount"],
                    snapshot["interest_rate"],
                    snapshot["term_months"],
                    snapshot["monthly_installment"],
                    snapshot["total_repayment"],
                    snapshot["recommendation"],
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_dict(row)


def get_latest_loan_application(uid: str) -> dict | None:
    """Most recent application submitted by this user, or None if they haven't applied yet."""
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM loan_applications WHERE uid = %s ORDER BY created_at DESC LIMIT 1",
                (uid,),
            )
            row = cur.fetchone()
    return _row_to_dict(row) if row else None


def get_loan_application(application_id: int) -> dict | None:
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM loan_applications WHERE id = %s", (application_id,))
            row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_applications_by_status(status_value: str) -> list[dict]:
    """
    All applications currently sitting in `status_value`, oldest first -- used
    by the admin dashboard to list applications awaiting a final
    approve/reject disbursement decision (see api_routes.py's
    `/loan-application` for how a row reaches `submitted`).
    """
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM loan_applications WHERE status = %s ORDER BY created_at ASC",
                (status_value,),
            )
            rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def attach_guarantor_relationship(application_id: int, relationship_id: str) -> dict | None:
    """Link a just-requested digital guarantor relationship to this application."""
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE loan_applications
                SET guarantor_relationship_id = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (relationship_id, application_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_dict(row) if row else None


def update_status_by_relationship(relationship_id: str, status: str) -> dict | None:
    """
    Called from the admin guarantor decision (admin_routes.py) to move any
    application linked to this relationship forward: `submitted` once the
    guarantor is admin-approved, or back to `awaiting_guarantor` if rejected
    so the applicant can line up a different guarantor.
    """
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE loan_applications
                SET status = %s, updated_at = now()
                WHERE guarantor_relationship_id = %s
                RETURNING *
                """,
                (status, relationship_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_dict(row) if row else None


def update_admin_decision(application_id: int, status_value: str, reason: str | None) -> dict | None:
    """
    Record the admin's final disbursement decision on a `submitted`
    application, moving it to a terminal state (`approved` or
    `admin_rejected`). Only applies when the row is still `submitted` --
    returns None if it has already moved on (e.g. a concurrent decision).
    """
    with psycopg2.connect(_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE loan_applications
                SET status = %s, admin_decision_reason = %s, updated_at = now()
                WHERE id = %s AND status = 'submitted'
                RETURNING *
                """,
                (status_value, reason, application_id),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_dict(row) if row else None

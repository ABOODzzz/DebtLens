---
name: DebtLens loan application flow
description: How the end-to-end "apply for financing" journey connects eligibility assessment, Postgres persistence, and the digital guarantor network.
---

The full loan-application journey (submit amount/purpose -> AI eligibility -> optional digital guarantor) spans two data stores that must stay in sync:

- `loan_applications` (Postgres, via `loan_application_store.py`) is the application record itself: requested amount, purpose, status, and a snapshot of the eligibility verdict at submission time.
- `guarantorRelationships` (Firestore, via `guarantor.py`) is the guarantor request/response/admin-decision record, unrelated in storage but cross-linked by `loan_applications.guarantor_relationship_id` (text column holding the Firestore doc id).

**Why:** these features were built independently (guarantor network first, loan application second) and reusing the existing consolidation-requests Postgres pattern was simpler than migrating guarantor relationships into Postgres or vice versa.

**How to apply:** `status` on a loan application is deterministic, not AI-decided — computed from the existing DTI ceiling constants in `api_routes.py` (`_LOAN_ASSESSMENT_DTI_CEILING_PERCENT` = 45%, `_GUARANTOR_DTI_CEILING_PERCENT` = 50%) via `_decide_requires_guarantor`: DTI <= 45% -> `submitted`; 45% < DTI <= 50% (and not already guarantor-backed) -> `awaiting_guarantor`; otherwise -> `rejected`. When a guarantor request is made with an `application_id`, `guarantor.py`'s `/request` endpoint attaches the relationship id to the application; when an admin later approves/rejects that relationship (`admin_routes.py`), it flips the application back to `submitted` or `awaiting_guarantor`. There is currently no final admin disbursement decision on `submitted` applications — that's an open follow-up (see project task "Let admins make the final call on loan applications backed by a guarantor").

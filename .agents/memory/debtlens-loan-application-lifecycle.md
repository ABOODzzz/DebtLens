---
name: DebtLens loan_applications lifecycle & test mocking gotcha
description: Status flow for the Postgres loan_applications table through the final admin decision, and a monkeypatching pitfall in admin_routes.py's function-local imports.
---

The `loan_applications` Postgres table (lib/db/src/schema/loanApplications.ts, server_py/loan_application_store.py) walks: `ineligible`/`awaiting_guarantor`/`submitted` (initial AI assessment) → optionally `awaiting_guarantor` → `submitted` once any required guarantor is admin-approved (server_py/admin_routes.py's guarantor_decision calls `update_status_by_relationship`) → terminal `approved`/`admin_rejected` via a *separate* final disbursement decision (`loan_application_decision` endpoint, `update_admin_decision`). `rejected` is also terminal (ineligible even with a guarantor).

**Why:** the guarantor being approved only proves the guarantor is viable — it is not itself a disbursement decision. Only an admin's explicit final call moves `submitted` to a terminal state, mirroring the "guarantor acceptance ≠ final approval" precedent from the guarantor flow itself.

**How to apply:** any new terminal state or status transition must update: `lib/db/src/schema/loanApplications.ts` (comment + default), `lib/api-spec/openapi.yaml`'s `LoanApplication.status` enum, `loan_application_store.py`, `admin_routes.py`, dashboard.tsx's `loanApplicationStatusLabel`/`Class`, and the pytest contract tests in `server_py/tests/test_loan_application_contract.py` / `test_admin_loan_application_contract.py`.

A terminal decision (`approved`/`admin_rejected`) can be walked back via a separate revise endpoint/store function (distinct from the original decision one) that only accepts rows already in a terminal state, requires a reason, and enforces a time window from `updated_at` so it can't relitigate old settled cases; the revise notification must reach the customer and, if a guarantor relationship is attached, the guarantor too.

Guarantor-driven application changes must use compare-and-set transitions between `awaiting_guarantor` and `submitted`; a finalized application must win over a correction rather than being downgraded.

**Why:** a guarantor correction and the final disbursement decision can race, and the final decision is authoritative once recorded.

**How to apply:** keep the expected current status in the same SQL `UPDATE` predicate and surface whether the transition happened or was intentionally skipped.

Test-mocking pitfall: `admin_routes.py` does `import loan_application_store` (and `from notifications import notify`) *inside* each route function body, not at module top level. `monkeypatch.setattr(admin_routes, "loan_application_store", fake)` therefore has no effect — the function's inline import always resolves to the real module via `sys.modules`. Tests must instead monkeypatch attributes on the actual `loan_application_store`/`notifications` module objects (e.g. `monkeypatch.setattr(loan_application_store, "get_loan_application", fake_fn)`).

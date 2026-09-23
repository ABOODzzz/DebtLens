---
name: DebtLens finance endpoint contract tests
description: How /analyze, /restructure, /advice responses are checked against the OpenAPI schema and the dashboard dialogs that consume them.
---

DebtLens has a pytest contract test (`artifacts/debt-lens/server_py/tests/test_finance_contract.py`, registered as validation `debt-lens-contract-tests`) that calls `/api/analyze`, `/api/restructure`, `/api/advice` via FastAPI's `TestClient`, with `get_current_user` overridden via `app.dependency_overrides` and `api_routes.get_user_financial_profile` / `api_routes.anthropic_client` monkeypatched to fixed fakes (no real Firebase/Anthropic calls). It validates each JSON response against the matching schema in `lib/api-spec/openapi.yaml` (loaded with `jsonschema.RefResolver.from_schema`) and additionally asserts the exact fields `dashboard.tsx`'s dialogs read are present and non-empty, since the OpenAPI schema alone doesn't forbid an empty string/list slipping through.

**Why:** these three endpoints previously had no automated check tying the backend response shape to what the dashboard dialogs actually render — a field rename/drop could silently blank a dialog with only manual QA catching it.

**How to apply:** when adding/changing a field in `/analyze`, `/restructure`, `/advice`, or a new endpoint whose response feeds a dashboard dialog, extend this test file (or add a sibling test) following the same pattern: monkeypatch the profile/AI client, hit the endpoint, validate against the OpenAPI schema, then assert the dashboard-consumed fields are non-empty. Python test deps (pytest, httpx, jsonschema, pyyaml) live in the root `pyproject.toml`, not `artifacts/debt-lens/server_py/requirements.txt`.

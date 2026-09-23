---
name: DebtLens eligibility contract & frontend/backend method mismatch
description: What broke the /ai-loan-assessment (eligibility) endpoint before its contract test existed, and the general lesson about verifying HTTP method, not just response shape.
---

The generated frontend client (lib/api-client-react) calls the HTTP method declared in openapi.yaml (e.g. POST for /ai-loan-assessment), but a FastAPI route decorator (`@router.get`/`@router.post` in server_py/api_routes.py) can silently drift out of sync with the spec. A contract test that only hits the endpoint with `TestClient` using the same method the route happens to implement will never catch this — it must use the method the real generated client actually sends, or a 405-in-production bug goes undetected.

Also: this codebase's OpenAPI schemas mix two nullable styles — the correct OpenAPI 3.1 `type: ["number", "null"]` (used almost everywhere) vs. the OpenAPI 3.0 `type: number` + `nullable: true` (invalid under a 3.1 JSON Schema validator, since `jsonschema`/draft2020-12 ignores `nullable` and enforces the base type strictly). A schema written in the 3.0 style will fail contract-test validation the moment a field is legitimately null. Grep for `nullable: true` in lib/api-spec/openapi.yaml if a new nullable field is added; convert to the `type: [X, "null"]` form instead.

**Why:** Found while adding a contract test for the eligibility dialog (EligibilityDialog in dashboard.tsx) — the endpoint was actually broken in production (405) because the route was `@router.get` while the client always POSTs.

**How to apply:** When writing a new contract test for any DebtLens endpoint, call it with the method the generated `lib/api-client-react` hook actually uses (check `getXxxUrl`/the hook's `method:` in `lib/api-client-react/src/generated/api.ts`), not just whatever the route decorator says.

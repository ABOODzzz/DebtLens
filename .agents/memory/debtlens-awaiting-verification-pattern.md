---
name: DebtLens gated-endpoint pattern
description: How endpoints that gate on an unverified data source must stay schema-conforming, method-consistent, and crash-safe across the FastAPI backend, shared OpenAPI contract, and any other consumer of that contract.
---

Several DebtLens API endpoints short-circuit with a placeholder response
when the caller doesn't have admin-verified data yet. Two valid strategies
exist for this, and either one must stay consistent across every layer that
touches the shared OpenAPI contract, not just the endpoint being fixed:

1. **Always fully populate**: compute honest defaults so the response always
   satisfies its schema, with no special-cased shape. Best when the result
   type doesn't inherently depend on having real data.
2. **Optional flag + partial schema**: add a required boolean flag plus an
   optional message field to the schema, move every other field in that
   schema out of `required`, and have every consumer of the generated client
   type check the flag before reading other fields.

**Why this bit us:** a gated endpoint returned a placeholder shape that
wasn't in the OpenAPI schema at all, while the schema declared unrelated
fields as required — so the generated TypeScript type claimed those fields
always existed, and the frontend crashed reading `undefined`. Separately,
the generated client's HTTP method (from the spec) didn't match the actual
route's method on the backend, so the fix was unreachable until that was
caught too.

**How to apply:** when changing a shared OpenAPI schema, grep the whole
monorepo for every generated-client consumer of it (multiple backends can
share one contract) and update each one, not just the primary target.
Also double check that the route's registered HTTP verb matches what the
spec (and therefore the generated client) actually calls — a schema fix is
invisible if the request never reaches the handler.

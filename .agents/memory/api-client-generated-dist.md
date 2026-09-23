---
name: Shared API client generated declarations
description: Workspace frontend typechecks consume the API client's built declarations, which can lag behind generated source after OpenAPI changes.
---

When the OpenAPI contract or generated API client changes, regenerate the client and run the workspace library typecheck before checking an artifact frontend. The artifact may resolve `lib/api-client-react/dist` declarations even though the source under `lib/api-client-react/src` is already current.

**Why:** Artifact typechecks can report missing hooks or schemas that are present in generated source when the shared package's declaration output is stale.

**How to apply:** Run the API spec codegen script, which also runs the workspace library typecheck, before diagnosing missing exports as application-code errors.
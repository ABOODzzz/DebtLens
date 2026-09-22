---
name: Firebase Storage rules via REST
description: How to deploy Firebase Storage security rules without the Firebase CLI, using only the existing service account.
---

New Firebase projects default Storage rules to deny all reads/writes. If a project uses `firebase-admin` on the server (service account JSON in `FIREBASE_SERVICE_ACCOUNT_KEY`) and the client SDK writes directly to Storage, uploads will fail with `storage/unauthorized` until rules are deployed — and there is no Firebase CLI/login available in this environment to run `firebase deploy`.

**How to apply:** Deploy rules directly via the `firebaserules.googleapis.com` REST API using an OAuth token minted from the service account (`credential.getAccessToken()` from `firebase-admin/app`'s `cert()`), no `firebase-tools` needed:
1. `POST projects/{projectId}/rulesets` with `{ source: { files: [{ name: "storage.rules", content: "<rules>" }] } }` → returns a ruleset name.
2. `PATCH projects/{projectId}/releases/firebase.storage/{bucketName}` (bucket like `<project>.firebasestorage.app` or `.appspot.com`, from `VITE_FIREBASE_STORAGE_BUCKET` or similar env var) with `{ release: { name, rulesetName } }`. If PATCH 404s because the release doesn't exist yet, fall back to `POST projects/{projectId}/releases`.

Run this as a throwaway Node script placed inside a workspace package that already has `firebase-admin` installed (module resolution needs it in that package's node_modules) — do not print the service account contents.

**Separately:** Firebase Storage uploads can also fail with `storage/quota-exceeded` (HTTP 402) even after rules are correctly configured — this means the project's Spark (free) plan storage/bandwidth quota is exhausted and requires the user to upgrade to the Blaze plan or free up storage in the Firebase console. This is a billing/plan issue, not a rules or code bug — don't debug it as one.

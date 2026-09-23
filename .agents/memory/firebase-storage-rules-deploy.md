---
name: Firebase Storage rules via REST
description: How to deploy Firebase Storage/Firestore security rules without the Firebase CLI, using only the existing service account.
---

New Firebase projects default Storage rules to deny all reads/writes. If a project uses `firebase-admin` on the server (service account JSON in `FIREBASE_SERVICE_ACCOUNT_KEY`) and the client SDK writes directly to Storage, uploads will fail with `storage/unauthorized` until rules are deployed — and there is no Firebase CLI/login available in this environment to run `firebase deploy`.

**How to apply:** Deploy rules directly via the `firebaserules.googleapis.com` REST API using an OAuth token minted from the service account (`credential.getAccessToken()` from `firebase-admin/app`'s `cert()`), no `firebase-tools` needed:
1. `POST projects/{projectId}/rulesets` with `{ source: { files: [{ name: "<storage.rules|firestore.rules>", content: "<rules>" }] } }` → returns a ruleset name.
2. `PATCH projects/{projectId}/releases/<release-name>` with `{ release: { name, rulesetName } }`. If PATCH 404s because the release doesn't exist yet, fall back to `POST projects/{projectId}/releases`.
   - Storage release name: `projects/{projectId}/releases/firebase.storage/{bucketName}` (bucket like `<project>.firebasestorage.app`, from `VITE_FIREBASE_STORAGE_BUCKET` or similar env var).
   - Firestore release name: `projects/{projectId}/releases/cloud.firestore` (default database).

Run this as a throwaway Node script placed inside a workspace package that already has `firebase-admin` installed (module resolution needs it in that package's node_modules) — do not print the service account contents.

**Separately, a distinct failure mode:** Firebase Storage uploads can fail with `storage/quota-exceeded` (HTTP 402) even with correct rules — this means the project is still on the Spark (free) plan quota, or was recently upgraded to Blaze but the storage backend hasn't picked up the billing link yet. This is a billing/GCP-project issue, not a rules or code bug. In one real case, the user had to confirm billing in the **Google Cloud Console** (not just the Firebase console's plan toggle) before the quota actually lifted — Firebase's "Blaze" indicator alone was not sufficient evidence that billing had propagated to the storage backend.

**Rules content is also a security surface, not just an access gate:** when a Firestore rule marks fields as server-only/protected (e.g. `reviewStatus`, `decidedAt`) via `!diff.affectedKeys().hasAny(protectedFields())`, audit client code for any direct `updateDoc`/`setDoc` call that writes those same fields — such calls will start failing with permission-denied once the rules are deployed, even if they "worked" before when rules were absent/permissive. Remove redundant client writes of server-decided fields; let the server's Admin SDK write (which bypasses rules) be the sole writer.

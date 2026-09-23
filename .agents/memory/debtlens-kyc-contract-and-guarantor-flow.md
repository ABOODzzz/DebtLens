---
name: DebtLens KYC contract and Digital Guarantor flow
description: Non-obvious contract/architecture facts for DebtLens KYC submission and the Digital Guarantor (الكفيل الرقمي) feature.
---

## KYC submit contract must match wizard.tsx, not be guessed
`server_py/kyc.py`'s `/api/kyc/submit` must accept `{profile: {fullName, nationalId}, photoPaths: [idFrontPath, idBackPath, selfiePath]}` (3 Firebase Storage paths, not URLs) because that's exactly what `src/pages/wizard.tsx` sends. A prior version used a different shape (`id_photo_url`/`selfie_url` as HTTP URLs) that silently 422'd on every real submission — openapi.yaml and the frontend were never actually exercised against it.

**Why:** the mismatch wasn't caught because nothing in the codebase cross-checks the Pydantic model against openapi.yaml/wizard.tsx at build time; it only surfaces when a real user submits KYC.

**How to apply:** before trusting any FastAPI request model in this app, diff it against both `lib/api-spec/openapi.yaml` and the actual frontend call site — don't assume the three agree.

## Guarantor images/photos are Storage paths, resolved to signed URLs on read
`kycVerification.idFrontPath/idBackPath/selfiePath` are Storage paths. Anywhere they need to be shown or downloaded (admin detail view, bank-request Claude analysis), resolve them via a `get_storage_bucket().blob(path)` + `generate_signed_url(...)` helper — never treat them as ready-to-fetch URLs.

## Digital Guarantor: admin has final say, not the named guarantor
Flow is: requester names a guarantor by national ID → guarantor accepts (status becomes `awaiting_admin_review`, NOT `approved`) → admin reviews both parties' identity + financials (with an AI risk comparison) and makes the final approve/reject call, which is what actually sets `guarantorUid`.

**Why:** explicit product decision — a customer-to-customer guarantee isn't legally binding, so admin must be in the loop before it affects loan terms, matching the KYC manual-override pattern already used elsewhere in the app.

**How to apply:** any change to guarantor status transitions must preserve this two-step gate (guarantor acceptance != final approval).

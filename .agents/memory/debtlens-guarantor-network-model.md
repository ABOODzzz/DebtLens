---
name: DebtLens multi-guarantor network model
description: How the Digital Guarantor feature models many-to-many relationships, capacity limits, and admin approval, plus the notifications collection it shares.
---

The Digital Guarantor system is a many-to-many network, not a single field on a user doc: every guarantor/requester pair lives as its own document in the top-level `guarantorRelationships` Firestore collection (fields `requesterUid`, `guarantorUid`, `status`, `maxAmount`, etc.). A user can appear in many relationship docs as either party.

**Why:** the original design was a single `guarantorUid`/`guarantorRequest` field per user, which only allowed one guarantor per person and one dependent per guarantor. The user explicitly asked for many-to-many.

**How to apply:** any new endpoint or query touching guarantors must go through `guarantorRelationships` (see `guarantor.py`'s `_relationships_for`/`_capacity` helpers), never re-add a `guarantorUid` field to the user doc. Status flow: `pending` → guarantor responds → `awaiting_admin_review` or `declined` → admin decides → `approved`/`rejected`. Only an admin decision activates a guarantee; the guarantor's own acceptance never does. Concurrent/exposure caps live as constants in `guarantor.py` (`GUARANTOR_MAX_CONCURRENT`, `GUARANTOR_MAX_TOTAL_EXPOSURE`, `REQUESTER_MAX_GUARANTORS`, `REQUESTER_MAX_TOTAL_BACKED`) and must be checked on both sides before creating a new relationship.

A generic `notifications` Firestore collection (see `notifications.py`) backs an in-app bell for any flow, not just guarantors — reuse its `notify()` helper (best-effort, never raises) instead of building a second notification mechanism.

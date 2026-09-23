---
name: DebtLens guarantor decision history
description: Durable rules for retaining and exposing final admin decisions and revisions on digital guarantor relationships.
---

Final admin guarantor decisions and later corrections must be appended atomically to the relationship's history rather than replacing a single latest-decision record. Each entry needs the prior status, new status, reason, timestamp, and admin UID.

**Why:** reviewers need an accountable, complete record even when a decision is corrected, and an atomic append prevents one concurrent update from silently overwriting another history entry.

**How to apply:** store the append-only history on the `guarantorRelationships` document with Firestore's array-union update, then normalize legacy/malformed entries out of the admin response while preserving chronological order.
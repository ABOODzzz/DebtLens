---
name: DebtLens manual-obligation analysis
description: Business rule for customers without bank statements and how their analysis and eligibility must be calculated.
---

Customers without bank accounts must never be assessed from synthetic/demo transactions. After they explicitly declare monthly obligations (including a valid zero-obligation declaration), comprehensive analysis, AI advice, dashboard totals, and financing eligibility use their self-reported monthly income minus those obligations.

**Why:** invented transactions can materially distort credit eligibility. The product requirement is to calculate affordability from the customer's actual declared rent, utilities, transport, loans, family costs, and other recurring commitments when bank evidence does not exist.

**How to apply:** preserve the distinction between “not declared yet” and “declared with total zero.” Eligibility calculations must use monthly normalized values, not sums across multiple statement months, and the server must continue enforcing the DTI ceiling independently of the model response.